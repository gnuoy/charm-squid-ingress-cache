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


class IngressCacheAvailableEvent(EventBase):
    pass


class IngressCacheCharmEvents(CharmEvents):
    """Custom charm events."""
    ingress_cache_available = EventSource(IngressCacheAvailableEvent)


class IngressCacheProvides(Object):
    """This class defines the functionality for the 'provides' side of the 'ingress' relation.

    Hook events observed:
        - relation-changed
    """
    CACHE_REQUIRED_CONFIG = {'service-hostname', 'service-name', 'service-port'}

    def __init__(self, charm):
        super().__init__(charm, "ingress_cache")
        # Observe the relation-changed hook event and bind
        # self.on_relation_changed() to handle the event.
        self.framework.observe(
            charm.on["ingress_cache"].relation_changed,
            self._on_relation_changed)
        self.charm = charm

    def relation_ready(self):
        try:
            relation = self.model.get_relation("ingress-cache")
        except KeyError:
            return False
        if relation and self.CACHE_REQUIRED_CONFIG.issubset(
                set(relation.data[relation.app].keys())):
            return True
        else:
            return False

    def _on_relation_changed(self, event):
        """Handle a change to the ingress relation.

        Confirm we have the fields we expect to receive."""
        # `self.unit` isn't available here, so use `self.model.unit`.
        if not self.model.unit.is_leader():
            return

        # Create an event that our charm can use to decide it's okay to
        # configure the ingress.
        if self.relation_ready():
            logger.info("cache relation ready")
            self.charm.on.ingress_cache_available.emit()
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
