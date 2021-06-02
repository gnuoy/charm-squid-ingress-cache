#!/usr/bin/env python3
# Copyright 2021 liam
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from ops.framework import EventBase, EventSource, Object
from ops.charm import CharmEvents

logger = logging.getLogger(__name__)

REQUIRED_INGRESS_RELATION_FIELDS = {
    "service-hostname",
    "service-name",
    "service-port",
}

OPTIONAL_INGRESS_RELATION_FIELDS = {
    "limit-rps",
    "limit-whitelist",
    "max-body-size",
    "retry-errors",
    "service-namespace",
    "session-cookie-max-age",
    "tls-secret-name",
    "path-routes",
}


class IngressCacheAvailableEvent(EventBase):
    pass


class IngressCacheCharmEvents(CharmEvents):
    """Custom charm events."""
    ingress_cache_available = EventSource(IngressCacheAvailableEvent)


class IngressBaseProvides(Object):
    CACHE_REQUIRED_CONFIG = {'service-hostname', 'service-name', 'service-port'}

    def get_relation(self):
        try:
            return self.model.get_relation(self.relation_name)
        except KeyError:
            return

    def get_complete_relation(self):
        relation = self.get_relation()
        if relation and self.CACHE_REQUIRED_CONFIG.issubset(
                set(relation.data[relation.app].keys())):
            return relation
        else:
            return None

    def get_relation_data_subset(self, keys):
        ingress_config = {}
        relation = self.get_complete_relation()
        if relation:
            ingress_proxy_relation_data = relation.data[relation.app]
            # Proxy ingress settings from cache client to ingress relation.
            for field in keys:
                if ingress_proxy_relation_data.get(field):
                    ingress_config[field] = ingress_proxy_relation_data[field]
        return ingress_config

    def get_ingress_data(self):
        ingress_config = self.get_relation_data_subset(
            REQUIRED_INGRESS_RELATION_FIELDS.union(
                OPTIONAL_INGRESS_RELATION_FIELDS))
        if ingress_config:
            ingress_config['service-name'] = self.model.app.name
        return ingress_config

    def _on_relation_changed(self, event):
        """Handle a change to the ingress relation.

        Confirm we have the fields we expect to receive."""
        # `self.unit` isn't available here, so use `self.model.unit`.
        if not self.model.unit.is_leader():
            return

        # Create an event that our charm can use to decide it's okay to
        # configure the ingress.
        if self.get_complete_relation():
            self._emit_available(event)
        else:
            logger.error("Cache relation incomplete")

    def get_cache_peers(self, domain="svc.cluster.local"):
        cache_peers = []
        relation = self.model.get_relation("ingress-cache")
        if relation:
            svc_name = relation.data[relation.app]["service-name"]
            for peer in relation.units:
                cache_peers.append(
                    f"{peer.name}.{svc_name}-endpoints.{self.model.name}.{domain}")
        return cache_peers


class IngressProxyAvailableEvent(EventBase):
    pass


class IngressCacheProvides(IngressBaseProvides):
    """This class defines the functionality for the 'provides' side of the 'ingress' relation.

    Hook events observed:
        - relation-changed
    """
    on = IngressCacheCharmEvents()

    def __init__(self, charm):
        super().__init__(charm, "ingress_cache")
        self.relation_name = "ingress-cache"
        # Observe the relation-changed hook event and bind
        # self.on_relation_changed() to handle the event.
        self.framework.observe(
            charm.on["ingress_cache"].relation_changed,
            self._on_relation_changed)
        self.charm = charm

    def _emit_available(self, event):
        logger.info("cache relation ready")
        self.on.ingress_cache_available.relation_event = event
        self.on.ingress_cache_available.emit()

    def get_cache_data(self):
        ingress_config = self.get_relation_data_subset(['refresh-patterns'])
        return ingress_config


class IngressProxyCharmEvents(CharmEvents):
    """Custom charm events."""
    ingress_proxy_available = EventSource(IngressProxyAvailableEvent)


class IngressProxyProvides(IngressBaseProvides):
    """This class defines the functionality for the 'provides' side of the 'ingress' relation.

    Hook events observed:
        - relation-changed
    """
    CACHE_REQUIRED_CONFIG = {'service-hostname', 'service-name', 'service-port'}
    on = IngressProxyCharmEvents()

    def __init__(self, charm):
        super().__init__(charm, "ingress_proxy")
        self.relation_name = "ingress-proxy"
        # Observe the relation-changed hook event and bind
        # self.on_relation_changed() to handle the event.
        self.framework.observe(
            charm.on["ingress_proxy"].relation_changed,
            self._on_relation_changed)
        self.charm = charm

    def _emit_available(self, event):
        logger.info("cache relation ready")
        self.on.ingress_proxy_available.relation_event = event
        self.on.ingress_proxy_available.emit()
