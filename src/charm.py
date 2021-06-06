#!/usr/bin/env python3
# Copyright 2021 Canonical
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm for deploying squid-ingress-cache"""

import jinja2
import json
import logging

# from typing import Union

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.pebble import PathError
# from ops.model import ActiveStatus, BlockedStatus, Relation
from ops.model import ActiveStatus, BlockedStatus
from squid_templates import SQUID_TEMPLATE
from charms.nginx_ingress_integrator.v0.ingress import (
    IngressRequires,
    IngressProxyProvides,
    REQUIRED_INGRESS_RELATION_FIELDS,
    OPTIONAL_INGRESS_RELATION_FIELDS,
    IngressCharmEvents,
)

logger = logging.getLogger(__name__)


class SquidIngressCacheCharm(CharmBase):
    """Squid Ingreess proxy charm."""

    _stored = StoredState()
    on = IngressCharmEvents()
    SQUID_CONFIG_OPTIONS = ['log_format']

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(
            squid_pebble_ready=False,
        )
        # The register event handlers
        self.ingress_proxy_provides = IngressProxyProvides(
            self
        )
        self.ingress = IngressRequires(
            self,
            self._get_ingress_config(),
        )
        self.framework.observe(
            self.on.squid_pebble_ready,
            self._squid_pebble_ready)
        self.framework.observe(
            self.on.ingress_available,
            self._ingress_proxy_available)
        self.framework.observe(
            self.on.update_status,
            self._assess_charm_state)

    def _squid_pebble_ready(self, event) -> None:
        self._stored.squid_pebble_ready = True
        self._configure_charm(event)

    def _ingress_proxy_available(self, event) -> None:
        self._configure_charm(event)

    def _assess_charm_state(self, event):
        """Check if charm is ready to enable service.

        Side-effect: Updates the charms workload status.
        """
        if not self._get_ingress_config_from_relation():
            logger.warning("Ingress proxy relation missing or incomplete")
            self.unit.status = BlockedStatus(
                'Ingress proxy relation missing or incomplete')
            return False
        if not self._stored.squid_pebble_ready:
            logger.warning("Pebble not ready")
            self.unit.status = BlockedStatus('Pebble not ready')
            return False
        self.unit.status = ActiveStatus()
        logger.info("Charm ready")
        return True

    def _configure_charm(self, event) -> None:
        """Configure service if minimum requirements are met."""
        if self._assess_charm_state(event):
            squid_config = self._get_squid_config()
            self._configure_pebble(event)
            self._render_config(squid_config)
            self.ingress.update_config(self._get_ingress_config())

    def _get_squid_config(self) -> str:
        """Generate squid.conf contents."""
        jinja_env = jinja2.Environment(loader=jinja2.BaseLoader())
        jinja_template = jinja_env.from_string(SQUID_TEMPLATE)
        ingress_config = self._get_ingress_config()
        squid_config = self._get_squid_config_from_relation()
        ctxt = {
            'port': ingress_config['service-port'],
            'peers': self._get_cache_peers()}
        for k in self.SQUID_CONFIG_OPTIONS:
            ctxt[k] = self.config[k]
        ctxt.update(squid_config)
        ctxt = {k.replace('-', '_'): v for k, v in ctxt.items()}
        return jinja_template.render(**ctxt)

    def _restart_squid(self):
        container = self.unit.get_container("squid")
        logger.info("Restarting squid")
        if container.get_service("squid").is_running():
            container.stop("squid")
        container.start("squid")

    def _render_config(self, squid_config) -> None:
        """Push squid.conf to payload container."""
        logger.info("Pushing new squid.conf")
        logger.info(squid_config)
        container = self.unit.get_container("squid")
        try:
            existing_config = container.pull("/etc/squid/squid.conf").read()
        except (PathError, NotImplementedError):
            existing_config = ''
        # XXX This try/except is to handle the fact that push is not
        #     implemented in the test hareess yet.
        try:
            container.push("/etc/squid/squid.conf", squid_config)
        except NotImplementedError:
            logger.error("Could not push /etc/squid/squid.conf to container")
        if existing_config != squid_config:
            logger.info("Config change detected, restarting squid")
            self._restart_squid()

    def _configure_pebble(self, event) -> None:
        """Define and start squid using the Pebble API. """
        # Get a reference the container attribute on the PebbleReadyEvent
        container = self.unit.get_container("squid")
        existing_plan = container.get_plan().to_dict()
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "squid layer",
            "description": "pebble config layer for squid",
            "services": {
                "squid": {
                    "override": "replace",
                    "summary": "squid service",
                    "command": "/usr/sbin/squid -N",
                    "startup": "enabled",
                }
            },
        }
        if existing_plan.get('services') != pebble_layer['services']:
            # Add intial Pebble config layer using the Pebble API
            container.add_layer("squid", pebble_layer, combine=True)
            # Autostart any services that were defined with startup: enabled
            container.autostart()

    def _get_data_from_relation(self, relation_name, required_keys, optional_keys=None) -> dict:
        """Return subset of relation data from existing relation.

        If a relation with `relation_name` exists and all the keys specified
        in `required_keys` are present on the relation then return a subset of
        the relation data corresponding to `required_keys`.
        """
        data = {}
        optional_keys = optional_keys or []
        relation = self.model.get_relation(relation_name)
        if relation:
            data = {k: relation.data[relation.app].get(k)
                    for k in list(required_keys) + list(optional_keys)
                    if relation.data[relation.app].get(k)}
        if set(required_keys).issubset(set(data)):
            return data
        else:
            return {}

    def _get_ingress_config(self) -> dict:
        default_config = {
            "service-hostname": self.app.name,
            "service-port": 3128,
        }
        config = self._get_ingress_config_from_relation() or default_config
        config['service-name'] = self.app.name
        config.pop('cache-settings', None)
        return config

    def _get_cache_peers(self, domain="svc.cluster.local") -> list:
        relation = self.model.get_relation('ingress-proxy')
        cache_peers = []
        svc_name = relation.data[relation.app]["service-name"]
        for peer in relation.units:
            unit_name = peer.name.replace('/', '-')
            cache_peers.append(
                f"{unit_name}.{svc_name}-endpoints.{self.model.name}.{domain}")
        return cache_peers

    def _get_ingress_config_from_relation(self) -> dict:
        return self._get_data_from_relation(
            'ingress-proxy',
            REQUIRED_INGRESS_RELATION_FIELDS,
            OPTIONAL_INGRESS_RELATION_FIELDS)

    def _get_squid_config_from_relation(self) -> dict:
        cache_settings = {}
        relation_data = self._get_data_from_relation(
            'ingress-proxy',
            ['cache-settings'])
        try:
            cache_settings = json.loads(relation_data['cache-settings'])
        except KeyError:
            pass
        return cache_settings


if __name__ == "__main__":
    main(SquidIngressCacheCharm)
