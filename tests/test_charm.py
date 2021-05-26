# Copyright 2021 liam
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
# from unittest.mock import Mock

from charm import SquidCacheCharm
from ops.model import ActiveStatus
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(SquidCacheCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

#    def test_config_changed(self):
#        self.assertEqual(list(self.harness.charm._stored.things), [])
#        self.harness.update_config({"thing": "foo"})
#        self.assertEqual(list(self.harness.charm._stored.things), ["foo"])

#    def test_action(self):
#        # the harness doesn't (yet!) help much with actions themselves
#        action_event = Mock(params={"fail": ""})
#        self.harness.charm._on_fortune_action(action_event)
#
#        self.assertTrue(action_event.set_results.called)
#
#    def test_action_fail(self):
#        action_event = Mock(params={"fail": "fail this"})
#        self.harness.charm._on_fortune_action(action_event)
#
#        self.assertEqual(action_event.fail.call_args, [("fail this",)])

    def add_cache_relation(self):
        rel_id = self.harness.add_relation('ingress-proxy', 'squid-cache')
        self.harness.add_relation_unit(
            rel_id,
            'squid-cache')
        self.harness.update_relation_data(
            rel_id,
            'squid-cache',
            {
                'service-hostname': 'mydomain.external.com',
                'service-name': 'website',
                'service-port': 80,
                'limit-rps': 12,
            })
        return rel_id

    def test_get_cache_peers(self):
        self.add_cache_relation()
        # self.model.name is None in test harness.
        self.assertEqual(
            self.harness.charm.get_cache_peers(
                self.harness.model.get_relation("ingress-proxy")),
            ['squid-cache.website-endpoints.None.svc.cluster.local'])

    def test_httpbin_pebble_ready(self):
        # Check the initial Pebble plan is empty
        initial_plan = self.harness.get_container_pebble_plan("squid")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")
        # Expected plan after Pebble ready with default config
        self.add_cache_relation()
        expected_plan = {
            "services": {
                "squid": {
                    "override": "replace",
                    "summary": "squid service",
                    "command": "/usr/sbin/squid -N",
                    "startup": "enabled",
                }
            },
        }
        # Get the httpbin container from the model
        container = self.harness.model.unit.get_container("squid")
        # Emit the PebbleReadyEvent carrying the httpbin container
        self.harness.charm.on.squid_pebble_ready.emit(container)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("squid").to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        service = self.harness.model.unit.get_container("squid").get_service("squid")
        self.assertTrue(service.is_running())
        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_ingress_proxy_relation_ready(self):
        # Check False when there is no cache relation.
        self.assertFalse(self.harness.charm.ingress_proxy_relation_ready())
        rel_id = self.harness.add_relation('ingress-proxy', 'squid-cache')
        # Check False with a cache relation but no relation data.
        self.assertFalse(self.harness.charm.ingress_proxy_relation_ready())
        self.harness.add_relation_unit(
            rel_id,
            'squid-cache')
        self.harness.update_relation_data(
            rel_id,
            'squid-cache',
            {
                'service-name': 'website',
                'service-port': 80,
            })
        # Check False with a cache relation but incomplete relation data.
        self.assertFalse(self.harness.charm.ingress_proxy_relation_ready())
        self.harness.update_relation_data(
            rel_id,
            'squid-cache',
            {
                'service-hostname': 'mydomain.external.com',
                'service-name': 'website',
                'service-port': 80,
            })
        # Check True with a cache relation and all relation data.
        self.assertTrue(self.harness.charm.ingress_proxy_relation_ready())

    def test_get_ingress_config(self):
        self.assertEqual(
            self.harness.charm.get_ingress_config(),
            {
                'service-hostname': 'squid-cache',
                'service-name': 'squid-cache',
                'service-port': 3128})
        self.add_cache_relation()
        self.assertEqual(
            self.harness.charm.get_ingress_config(),
            {
                'service-hostname': 'mydomain.external.com',
                'service-name': 'squid-cache',
                'limit-rps': 12,
                'service-port': 80})
