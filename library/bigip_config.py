#!/usr/bin/python

"""
ansible module for managing configuration resources on BIG-IP over iControlREST.
"""

import sys
import json
import requests
from copy import deepcopy

from requests.exceptions import ConnectionError, HTTPError, Timeout, TooManyRedirects

class BigipConfig(object):
  def __init__(self, module):
    self.host = module.params["host"]
    self.user = module.params["user"]
    self.password = module.params["password"]
    self.state = module.params["state"]
    self.payload = json.loads(module.params["payload"])
    self.collection_path = module.params["collection_path"]
    self.resource_id = module.params["resource_id"]
    self.resource_key = module.params["resource_key"]

    self.hosturl = "https://%s" % self.host
    self.auth = (self.user, self.password)

  def _get_full_resource_id(self):
    if self.resource_id is not None:
      return self.resource_id
    else:
      # need to extract the id from payload
      return self.payload[self.resource_key]

  def _get_full_resource_path(self):
    return '%s/%s' % (self.collection_path, self._get_full_resource_id())

  def _get_safe_patch_payload(self):
    """
     Working around this error from tmsh:
      => {"code":400,"message":"\"network\" may not be specified in the context of the \"modify\" command.
       \"network\" may be specified using the following commands: create, list, show","errorStack":[]}
    """
    safe_payload = deepcopy(self.payload)
    
    if safe_payload.get("network", None) is not None:
      del safe_payload["network"]

    return safe_payload

  def resource_exists(self):
    #for collections that we want to patch (for example sys/global-settings)
    # there is no resource_key which we can use to determine existance
    if self.resource_key is None:
      return False

    exists = False
    (rc, out, err) = self.http("get", self.collection_path)

    if rc != 0:
      raise ValueError("Bad return code from HTTP GET. %s " % err)

    items = out.get("items", None)
    if items is not None:
      for i in items:
        if i[self.resource_key] == self.payload[self.resource_key]:
          exists = True
          break
    return exists

  def create_or_update_resource(self):
    # if it is a collection, we can just patch 
    if self.resource_key is None:
      return self.http("patch", self.collection_path, self.payload)
    else:
      if self.resource_exists():
        return self.update_resource()
      else:
        return self.create_resource()


  def create_resource(self):
    return self.http("post", self.collection_path, self.payload)

  def update_resource(self):
    #if self.resource_key is None:
    #  return self.http("patch", self.collection_path, self.payload)
    #else:
    return self.http("patch", self._get_full_resource_path(),
      self._get_safe_patch_payload())

  def delete_resource(self):
    return self.http("delete", self._get_full_resource_path())

  def http(self, method, host, payload=''):
    print 'HTTP %s %s: %s' % (method, host, payload)
    methodfn = getattr(requests, method.lower(), None)
    if method is None:
      raise NotImplementedError("requests module has not method %s " % method)
    try:
      if payload != '':
        request = methodfn(url='%s/%s' % (self.hosturl, host), data=json.dumps(payload), auth=self.auth, verify=False)
      else:
        request = methodfn(url='%s/%s' % (self.hosturl, host), auth=self.auth, verify=False)

      if request.status_code != requests.codes.ok:
        request.raise_for_status()

      rc = 0
      out = json.loads(request.text)
      err = ''
    except (ConnectionError, HTTPError, Timeout, TooManyRedirects) as e:
      rc = 1
      out = ''
      err = '%s. %s' % (e.message, json.loads(request.text))

    print 'HTTP %s returned: %s' % (method, request.text)

    return (rc, out, err)

def main():

  print 'main()'
  module = AnsibleModule(
    argument_spec = dict(
      state=dict(default='present', choices=['present', 'absent'], type='str'),
      user=dict(required=True, default=None, type='str'),
      host=dict(required=True, default=None, type='str'),
      password=dict(required=True, default=None, type='str'),
      collection_path=dict(required=False, default=None, type='str'),
      # specific to state=present
      payload=dict(required=False, default=None, type='str'),
      resource_id=dict(required=False, default=None, type='str'),
      resource_key=dict(required=False, default=None, type='str'),
    ),
    mutually_exclusive = [['resource_id','resource_key']],
    supports_check_mode=True
  )

  bigip_config = BigipConfig(module)

  rc = None
  out = ''
  err = ''
  result = {}
  result['collection_path'] = bigip_config.collection_path
  result['state'] = bigip_config.state
  
  if bigip_config.state == 'absent':
    if bigip_config.resource_exists():
      if module.check_mode:
        module.exit_json(changed=True)
      (rc, out, err) = bigip_config.delete_resource()
      if rc != 0:
        module.fail_json(name=bigip_config.collection_path, msg=err, rc=rc)
  elif bigip_config.state == 'present':
    (rc, out, err) = bigip_config.create_or_update_resource()
    
    if rc != 0:
      module.fail_json(name=bigip_config.collection_path, msg=err, rc=rc)

  if rc is None:
    result['changed'] = False
  else:
    result['changed'] = True
  if out:
    result['out'] = out
  if err:
    result['err'] = err

  module.exit_json(**result)

# import module snippets
from ansible.module_utils.basic import *
main()


