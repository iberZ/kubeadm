# -*- coding: utf-8 -*-

# Copyright 2018 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import yaml
import subprocess

import utils
import cluster_api
import vagrant_utils

def ansible_installed():
    """ check if ansible is installed """
    try:
        devnull = open(os.devnull)
        subprocess.Popen(['ansible-playbook', '-h'], stdout=devnull, stderr=devnull).communicate()
    except OSError as e:
        if e.errno == os.errno.ENOENT:
            return False
    return True

def write_inventory(machines):
    """ Creates the `tmp/inventory` file.
        The inventory file reflects the roles defined in machine sets """

    # generate host groups and extracts corresponding host_vars from machine attributes
    groups    = {'all': [] }
    host_vars = {}

    for m in machines:
        groups['all'].append(m.name)
        for role in m.roles:
            r = "%ss" % (role.lower())
            if r not in groups:
                groups[r] = []
            groups[r].append(m.name)

        host_vars[m.name] = {'node_ip': m.ip}

    # writes the `tmp/inventory` file
    if not os.path.exists(vagrant_utils.tmp_folder):
        os.makedirs(vagrant_utils.tmp_folder)

    inventory_file = os.path.join(vagrant_utils.tmp_folder, 'inventory')
    
    with open(inventory_file, 'w') as fh:
        fh.write('# Generated by kubeadm-playground\n')

        # writes the host_vars section at the top of the file
        for m, hv in host_vars.items():
            fh.write("\n%s" % (m))
            for k, v in hv.items():
                fh.write(" %s=%s" % (k, v))
        fh.write('\n')

        # writes the host groups section 
        for key, vals in groups.items():
            fh.write("\n[%s]\n" % (key))
            for val in vals:
                fh.write("%s\n" % (val))


class quoted(str):
    pass

def quoted_presenter(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')


def unicode_presenter(self, data):
    return self.represent_str(data.encode('utf-8'))

def write_extra_vars(cluster):
    """ Creates the `tmp/extra_vars.yml` file.
        Extra extra vars are computed as a merge between extra_vars defined 
        in the cluster api (highest priority) and a set of default extra vars 
        (lowest priority). """
    
    # NB. only the settings used in the test guide should be defined as a default here;
    # value for defaults extra vars should be mirrored from 'hack/ansible/group_vars/all/main.yml'
    default_extra_vars = {
        'kubernetes': {
                'vip': {
                    'fqdn': 'k8s.example.com',
                    'ip': '10.10.10.3'
                },
                'cni': {
                    'weavenet': {
                        'manifestUrl': quoted("https://cloud.weave.works/k8s/net?k8s-version=$(kubectl version | base64 | tr -d '\n')")
                    },
                    'flannel': {
                        'manifestUrl': 'https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml'
                    },
                    'calico': {
                        'manifestUrl': 'https://docs.projectcalico.org/v3.1/getting-started/kubernetes/installation/hosted/kubeadm/1.7/calico.yaml'
                    }
                }
            },
            'kubeadm': {
                'binary': '/usr/bin/kubeadm',
                'token': 'abcdef.0123456789abcdef'
            }
    }

    utils.dict_merge(default_extra_vars, cluster.extra_vars)
    cluster.extra_vars=default_extra_vars

    # writes the `tmp/extra_vars.yml` file
    if not os.path.exists(vagrant_utils.tmp_folder):
        os.makedirs(vagrant_utils.tmp_folder)

    extra_vars_file = os.path.join(vagrant_utils.tmp_folder, 'extra_vars.yml')
    
    yaml.add_representer(quoted, quoted_presenter)
    yaml.add_representer(unicode, unicode_presenter)
    with open(extra_vars_file, 'w') as outfile:
        yaml.dump(cluster.extra_vars, outfile, default_flow_style=False)

def run_ansible(playbook):
    """ Run ansible playbook via subprocess. 
    
        Ansible execution depends on following files that should be made available before
        - `tmp/inventory`           (generated by write_inventory)
        - `tmp/extra_vars.yml`      (generated by write_extra_vars)
        - `tmp/ssh_config`          (generated by vagrant_utils)
        - hack/ansible/ansible.cfg  (include in the code base)
        """
    try:
        ansible_env = os.environ.copy()
        ansible_env['ANSIBLE_CONFIG'] = os.path.join(vagrant_utils.ansible_folder, 'ansible.cfg')
        ansible_env['ANSIBLE_SSH_ARGS'] = os.getenv('ANSIBLE_SSH_ARGS', '')
        ansible_env['ANSIBLE_SSH_ARGS'] += " -F %s" % (os.path.join(vagrant_utils.tmp_folder, 'ssh_config')) 

        subprocess.call([
            'ansible-playbook', os.path.join(vagrant_utils.ansible_folder, "%s.yml" % (playbook)), 
            '-i', os.path.join(vagrant_utils.tmp_folder, 'inventory'), 
            '-e', "@%s" % (os.path.join(vagrant_utils.tmp_folder, 'extra_vars.yml'))
        ] , env=ansible_env)
    except Exception as e:
        raise RuntimeError('Error executing `ansible-playbook`: ' + repr(e))