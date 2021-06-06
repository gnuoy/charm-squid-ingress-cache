# Copyright 2021 Canoncial
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
# from unittest.mock import Mock
import json

from charm import SquidIngressCacheCharm
from ops.model import ActiveStatus
from ops.testing import Harness

import tests.test_data as test_data


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(SquidIngressCacheCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def add_ingress_relation(self, cache_data=None):
        rel_id = self.harness.add_relation(
            'ingress',
            'nginx-ingress-controller')
        self.harness.add_relation_unit(
            rel_id,
            'nginx-ingress-controller/0')
        return rel_id

    def add_ingress_proxy_relation(self, cache_data=None):
        rel_id = self.harness.add_relation(
            'ingress-proxy',
            'mywebsite')
        self.harness.add_relation_unit(
            rel_id,
            'mywebsite/0')
        relation_data = {
            'service-hostname': 'mydomain.external.com',
            'service-name': 'website',
            'service-port': 80,
            'limit-rps': 12}
        if cache_data:
            relation_data['cache-settings'] = cache_data
        self.harness.update_relation_data(
            rel_id,
            'mywebsite',
            relation_data)
        return rel_id

    def add_ingress_cache_relation(self):
        cache_relation_data = {
            'refresh-patterns': [
                {
                    'case_sensitive': False,
                    'regex': '^ftp:',
                    'min': 1440,
                    'percent': 20,
                    'max': 10080,
                    'options': ['override-expire']},
                {
                    'case_sensitive': True,
                    'regex': '(/cgi-bin/|\?)',
                    'min': 0,
                    'percent': 0,
                    'max': 0,
                    'options': []}]}
        self.add_ingress_proxy_relation(
            cache_data=json.dumps(cache_relation_data))

    def test__get_cache_peers(self):
        self.add_ingress_proxy_relation()
        # self.model.name is None in test harness.
        self.assertEqual(
            self.harness.charm._get_cache_peers(),
            ['mywebsite-0.website-endpoints.None.svc.cluster.local'])

    def test_httpbin_pebble_ready(self):
        # Check the initial Pebble plan is empty
        initial_plan = self.harness.get_container_pebble_plan("squid")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")
        # Expected plan after Pebble ready with default config
        self.add_ingress_proxy_relation()
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

    def test__get_ingress_config_proxy(self):
        self.assertEqual(
            self.harness.charm._get_ingress_config(),
            {
                'service-hostname': 'squid-ingress-cache',
                'service-name': 'squid-ingress-cache',
                'service-port': 3128})
        self.add_ingress_proxy_relation()
        self.assertEqual(
            self.harness.charm._get_ingress_config(),
            {
                'service-hostname': 'mydomain.external.com',
                'service-name': 'squid-ingress-cache',
                'limit-rps': 12,
                'service-port': 80})

    def test__get_ingress_config_cache(self):
        self.assertEqual(
            self.harness.charm._get_ingress_config(),
            {
                'service-hostname': 'squid-ingress-cache',
                'service-name': 'squid-ingress-cache',
                'service-port': 3128})
        self.add_ingress_cache_relation()
        self.assertEqual(
            self.harness.charm._get_ingress_config(),
            {
                'service-hostname': 'mydomain.external.com',
                'service-name': 'squid-ingress-cache',
                'limit-rps': 12,
                'service-port': 80})

    def test__get_squid_config_proxy(self):
        self.add_ingress_proxy_relation()
        self.assertEqual(
            self.harness.charm._get_squid_config(),
            test_data.SQUID_CONFIG1)

    def test__get_squid_config_cache(self):
        self.maxDiff = None
        self.add_ingress_cache_relation()
        self.assertEqual(
            self.harness.charm._get_squid_config(),
            test_data.SQUID_CONFIG2)

    def test__get_squid_config_from_relation(self):
        self.assertEqual(
            self.harness.charm._get_squid_config_from_relation(),
            {})
        self.add_ingress_cache_relation()
        self.maxDiff = None
        self.assertEqual(
            self.harness.charm._get_squid_config_from_relation(),
            {
                'refresh-patterns': [
                    {
                        'case_sensitive': False,
                        'max': 10080,
                        'min': 1440,
                        'options': ['override-expire'],
                        'percent': 20,
                        'regex': '^ftp:'},
                    {
                        'case_sensitive': True,
                        'max': 0,
                        'min': 0,
                        'options': [],
                        'percent': 0,
                        'regex': '(/cgi-bin/|\\?)'}]})
