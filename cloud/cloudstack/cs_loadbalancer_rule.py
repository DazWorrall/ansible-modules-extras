#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# (c) 2015, Darren Worrall <darren@iweb.co.uk>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: cs_loadbalancer_rule
short_description: Manages load balancer rules
description:
    - Add or remove load balancer rules
version_added: '2.0'
author: "Darren Worrall @dazworrall"
options:
  name:
    description:
      - The name of the load balancer rule
    required: true
  algorithm:
    description:
      - Load balancer algorithm
      - Required when using C(state=present).
    required: false
    choices: [ 'source', 'roundrobin', 'leastconn' ]
    default: null
  private_port:
    description:
      - The private port of the private ip address/virtual machine where the
        network traffic will be load balanced to
      - Required when using C(state=present).
    required: false
    default: null
  public_port:
    description:
      - The public port from where the network traffic will be load balanced from
      - Required when using C(state=present).
    required: true
    default: null
  public_ip:
    description:
      - Public ip address from where the network traffic will be load balanced from
    required: false
    default: null
  open_firewall:
    description:
      - Whether the firewall rule for public port should be created, while creating the new rule.
      - Use M(cs_firewall) for managing firewall rules.
    required: false
    default: false
  cidr:
    description:
      - CIDR (full notation) to be used for firewall rule if required
    required: false
    default: null
  project:
    description:
      - Name of the project the load balancer IP address is related to.
    required: false
    default: null
  state:
    description:
      - State of the instance.
    required: true
    default: 'present'
    choices: [ 'present', 'absent' ]
  domain:
    description:
      - Domain the rule is related to.
    required: false
    default: null
  account:
    description:
      - Account the rule is related to.
    required: false
    default: null
  zone:
    description:
      - Name of the zone in which the rule shoud be created.
      - If not set, default zone is used.
    required: false
    default: null
extends_documentation_fragment: cloudstack
'''

EXAMPLES = '''
# Create a load balancer rule
- local_action:
    module: cs_loadbalancer_rule
    name: balance_http
    public_ip: 1.2.3.4
    algorithm: leastconn
    public_port: 80
    private_port: 8080

# Delete a load balancer rule
- local_action:
    module: cs_loadbalancer_rule
    name: balance_http
    state: absent
'''

RETURN = '''
---
id:
  description: UUID of the rule.
  returned: success
  type: string
  sample: a6f7a5fc-43f8-11e5-a151-feff819cdc9f
zone:
  description: Name of zone the rule is related to.
  returned: success
  type: string
  sample: ch-gva-2
project:
  description: Name of project the rule is related to.
  returned: success
  type: string
  sample: Production
account:
  description: Account the rule is related to.
  returned: success
  type: string
  sample: example account
domain:
  description: Domain the rule is related to.
  returned: success
  type: string
  sample: example domain
'''


try:
    from cs import CloudStack, CloudStackException, read_config
    has_lib_cs = True
except ImportError:
    has_lib_cs = False

# import cloudstack common
from ansible.module_utils.cloudstack import *


class AnsibleCloudStackLBRule(AnsibleCloudStack):

    def __init__(self, module):
        super(AnsibleCloudStackLBRule, self).__init__(module)
        self.returns = {
            'publicip': 'public_ip',
            'publicport': 'public_port',
            'privateport': 'private_port',
            'algorithm': 'algorithm',
            'cidrlist': 'cidr',
        }

    def get_ip_address(self, ip_address, key=None):
        args = {}
        args['ipaddress'] = ip_address
        args['account'] = self.get_account(key='name')
        args['domainid'] = self.get_domain(key='id')
        args['projectid'] = self.get_project(key='id')
        ip_addresses = self.cs.listPublicIpAddresses(**args)

        if ip_addresses:
            self.ip_address = ip_addresses['publicipaddress'][0]
        return self._get_by_key(key, self.ip_address)

    def get_rule(self, **kwargs):
        rules = self.cs.listLoadBalancerRules(**kwargs)
        if rules:
            return rules['loadbalancerrule'][0]

    def _get_common_args(self):
        return {
            'account': self.get_account(key='name'),
            'domainid': self.get_domain(key='id'),
            'projectid': self.get_project(key='id'),
            'zoneid': self.get_zone(key='id'),
            'publicipid': self.get_ip_address(self.module.params.get('public_ip'), key='id'),
            'name': self.module.params.get('name'),
        }

    def create_lb_rule(self):
        args = self._get_common_args()
        rule = self.get_rule(**args)
        if not rule and not self.module.check_mode:
            args.update({
                'algorithm': self.module.params.get('algorithm'),
                'privateport': self.module.params.get('private_port'),
                'publicport': self.module.params.get('public_port'),
                'cidrlist': self.module.params.get('cidr'),
            })
            res = self.cs.createLoadBalancerRule(**args)
            if 'errortext' in res:
                self.module.fail_json(msg="Failed: '%s'" % res['errortext'])

            poll_async = self.module.params.get('poll_async')
            if poll_async:
                res = self.poll_job(res, 'loadbalancer')
            rule = res
            self.result['changed'] = True

        return rule

    def delete_lb_rule(self):
        args = self._get_common_args()
        rule = self.get_rule(**args)
        if rule and not self.module.check_mode:
            res = self.cs.deleteLoadBalancerRule(id=rule['id'])
            if 'errortext' in res:
                self.module.fail_json(msg="Failed: '%s'" % res['errortext'])
            poll_async = self.module.params.get('poll_async')
            if poll_async:
                res = self._poll_job(res, 'loadbalancer')
            self.result['changed'] = True
        return rule


def main():
    module = AnsibleModule(
        argument_spec = dict(
            name = dict(),
            algorithm = dict(choices=['source', 'roundrobin', 'leastconn'], required=False),
            private_port = dict(type='int', default=10, required=False),
            public_port = dict(type='int', default=10, required=False),
            state = dict(choices=['present', 'absent'], default='present'),
            public_ip = dict(required=False),
            cidr = dict(required=False),
            project = dict(default=None, required=False),
            open_firewall = dict(choices=BOOLEANS, default=False),
            zone = dict(default=None),
            domain = dict(default=None),
            account = dict(default=None),
            poll_async = dict(choices=BOOLEANS, default=True),
            api_key = dict(default=None),
            api_secret = dict(default=None, no_log=True),
            api_url = dict(default=None),
            api_http_method = dict(choices=['get', 'post'], default='get'),
            api_timeout = dict(type='int', default=10),
            api_region = dict(default='cloudstack'),
        ),
        required_together = (
            ['api_key', 'api_secret', 'api_url'],
        ),
        supports_check_mode=True
    )

    if not has_lib_cs:
        module.fail_json(msg="python library cs required: pip install cs")

    try:
        acs_lb_rule = AnsibleCloudStackLBRule(module)

        state = module.params.get('state')
        if state in ['absent']:
            rule = acs_lb_rule.delete_lb_rule()
        else:
            rule = acs_lb_rule.create_lb_rule()

        result = acs_lb_rule.get_result(rule)

    except CloudStackException, e:
        module.fail_json(msg='CloudStackException: %s' % str(e))

    module.exit_json(**result)

# import module snippets
from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
