#!/usr/bin/python
# -*- encoding: utf-8; py-indent-offset: 4 -*-

# Copyright: (c) 2022, Robin Gierse <robin.gierse@tribe29.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: user

short_description: Manage users in Checkmk.

# If this is part of a collection, you need to use semantic versioning,
# i.e. the version is of the form "2.5.0" and not "2.4".
version_added: "0.0.1"

description:
- Create and delete users within Checkmk.

extends_documentation_fragment: [tribe29.checkmk.common]

options:
    username:
        description: The user you want to manage.
        required: true
        type: str
    fullname:
        description: The alias or full name of the user.
        required: true
        type: str
    password:
        description: The password or secret for login.
        type: str
        default: /
    auth_type:
        description: The authentication type.
        type: str
        default: password
        choices: [password, secret]
    disable_login:
        description: The user can be blocked from login but will remain part of the site.
        The disabling does not affect notification and alerts.
        type: bool
        default: false
    email:
        description: The mail address of the user. Required if the user is a monitoring contact and receives notifications via mail.
        type: str
    fallback_contact:
        description: In case none of your notification rules handles a certain event a notification
        will be sent to the specified email.
        type: bool
        default: false
    pager_address:
        description: The pager address.
        type: str
    idle_timeout_duration:
        description: The duration in seconds of the individual idle timeout if individual is selected as idle timeout option.
        type: str
    idle_timeout_option:
        description: Specify if the idle timeout should use the global configuration, be disabled or use an individual duration
        type: str
        default: disable
        choices: [global, disable, individual]
    roles:
        description: The list of assigned roles to the user.
        type: raw
        default: {user}
    authorized_sites:
        description: The names of the sites the user is authorized to handle.
        type: raw
        default: {}
    contactgroups:
        description: Assign the user to one or multiple contact groups.
        If no contact group is specified then no monitoring contact will be created for the user.
        type: raw
        default: {all}
    disable_notifications:
        description: Option if all notifications should be temporarily disabled.
        type: bool
        default: false
    language:
        description: Configure the language to be used by the user in the user interface.
        Omitting this will configure the default language.
        type: str
        default: []
        choices: [en, de, ro]

author:
    - Robin Gierse (@robin-tribe29)
"""

EXAMPLES = r"""
# Create a user.
- name: "Create a user."
  tribe29.checkmk.user:
    server_url: "http://localhost/"
    site: "local"
    automation_user: "automation"
    automation_secret: "$SECRET"
    user_name: "my_user"
    folder: "/"
    state: "present"

# Create a user with IP.
- name: "Create a user with IP address."
  tribe29.checkmk.user:
    server_url: "http://localhost/"
    site: "local"
    automation_user: "automation"
    automation_secret: "$SECRET"
    user_name: "my_user"
    attributes:
      alias: "My user"
      ip_address: "x.x.x.x"
    folder: "/"
    state: "present"

# Create a user which is monitored on a distinct site.
- name: "Create a user which is monitored on a distinct site."
  tribe29.checkmk.user:
    server_url: "http://localhost/"
    site: "local"
    automation_user: "automation"
    automation_secret: "$SECRET"
    user_name: "my_user"
    attributes:
      site: "NAME_OF_DISTRIBUTED_USER"
    folder: "/"
    state: "present"
"""

RETURN = r"""
# These are examples of possible return values, and in general should use other names for return values.
message:
    description: The output message that the module generates. Contains the API response details in case of an error.
    type: str
    returned: always
    sample: 'User created.'
"""

import json
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url


def exit_failed(module, msg):
    result = {"msg": msg, "changed": False, "failed": True}
    module.fail_json(**result)


def exit_changed(module, msg):
    result = {"msg": msg, "changed": True, "failed": False}
    module.exit_json(**result)


def exit_ok(module, msg):
    result = {"msg": msg, "changed": False, "failed": False}
    module.exit_json(**result)


def get_current_user_state(module, base_url, headers):
    current_state = "unknown"
    current_explicit_attributes = {}
    current_folder = "/"
    etag = ""

    api_endpoint = "/objects/user_config/" + module.params.get("user_name")
    parameters = "?effective_attributes=true"
    url = base_url + api_endpoint + parameters

    response, info = fetch_url(module, url, data=None, headers=headers, method="GET")

    if info["status"] == 200:
        body = json.loads(response.read())
        current_state = "present"
        etag = info.get("etag", "")
        extensions = body.get("extensions", {})
        current_explicit_attributes = extensions.get("attributes", {})
        current_folder = "/%s" % extensions.get("folder", "")
        if "meta_data" in current_explicit_attributes:
            del current_explicit_attributes["meta_data"]

    elif info["status"] == 404:
        current_state = "absent"

    else:
        exit_failed(
            module,
            "Error calling API. HTTP code %d. Details: %s. Body: %s"
            % (info["status"], info["body"], body),
        )

    return current_state, current_explicit_attributes, current_folder, etag


def set_user_attributes(module, attributes, base_url, headers):
    api_endpoint = "/objects/user_config/" + module.params.get("user_name")
    params = {
        "attributes": attributes,
    }
    url = base_url + api_endpoint

    response, info = fetch_url(
        module, url, module.jsonify(params), headers=headers, method="PUT"
    )

    if info["status"] != 200:
        exit_failed(
            module,
            "Error calling API. HTTP code %d. Details: %s, "
            % (info["status"], info["body"]),
        )


def move_user(module, base_url, headers):
    api_endpoint = "/objects/user_config/%s/actions/move/invoke" % module.params.get(
        "user_name"
    )
    params = {
        "target_folder": module.params.get("folder", "/"),
    }
    url = base_url + api_endpoint

    response, info = fetch_url(
        module, url, module.jsonify(params), headers=headers, method="POST"
    )

    if info["status"] != 200:
        exit_failed(
            module,
            "Error calling API. HTTP code %d. Details: %s, "
            % (info["status"], info["body"]),
        )


def create_user(module, attributes, base_url, headers):
    api_endpoint = "/domain-types/user_config/collections/all"
    params = {
        "folder": module.params.get("folder", "/"),
        "user_name": module.params.get("user_name"),
        "attributes": attributes,
    }
    url = base_url + api_endpoint

    response, info = fetch_url(
        module, url, module.jsonify(params), headers=headers, method="POST"
    )

    if info["status"] != 200:
        exit_failed(
            module,
            "Error calling API. HTTP code %d. Details: %s, "
            % (info["status"], info["body"]),
        )


def delete_user(module, base_url, headers):
    api_endpoint = "/objects/user_config/" + module.params.get("user_name")
    url = base_url + api_endpoint

    response, info = fetch_url(module, url, data=None, headers=headers, method="DELETE")

    if info["status"] != 204:
        exit_failed(
            module,
            "Error calling API. HTTP code %d. Details: %s, "
            % (info["status"], info["body"]),
        )


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        server_url=dict(type="str", required=True),
        site=dict(type="str", required=True),
        automation_user=dict(type="str", required=True),
        automation_secret=dict(type="str", required=True, no_log=True),
        username=dict(required=True, type=str),
        fullname=dict(required=True, type=str),
        password=dict(type="str", default="/"),
        auth_type=dict(type="str", default="password", choices=["password", "secret"]),
        disable_login=dict(type="bool", default=False),
        email=dict(type="str"),
        fallback_contact=dict(type="bool", default=False),
        pager_address=dict(type="str"),
        idle_timeout_duration=dict(type="str"),
        idle_timeout_option=dict(type="str", default="disable", choices=["global", "disable",
                           "individual"]),
        roles=dict(type="raw", default=["user"]),
        authorized_sites=dict(type="raw", default=[]),
        contactgroups=dict(type="raw", default=["all"]),
        disable_notifications=dict(type="bool", default=False),
        language=dict(type="str", default=[], choices=[None, "en", "de", "ro"]),
        state=dict(type="str", default='present', choices=["present", "absent"]),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    # Use the parameters to initialize some common variables
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "Bearer %s %s"
        % (
            module.params.get("automation_user", ""),
            module.params.get("automation_secret", ""),
        ),
    }

    base_url = "%s/%s/check_mk/api/1.0" % (
        module.params.get("server_url", ""),
        module.params.get("site", ""),
    )

    exit_failed(module, "Not implemeted")

    # Determine desired state and attributes
    attributes = module.params.get("attributes", {})
    if attributes == []:
        attributes = {}
    state = module.params.get("state", "present")

    if "folder" in module.params:
        if not module.params["folder"].startswith("/"):
            module.params["folder"] = "/" + module.params["folder"]
    else:
        module.params["folder"] = "/"

    # Determine the current state of this particular user
    (
        current_state,
        current_explicit_attributes,
        current_folder,
        etag,
    ) = get_current_user_state(module, base_url, headers)

    # Handle the user accordingly to above findings and desired state
    if state == "present" and current_state == "present":
        headers["If-Match"] = etag
        msg_tokens = []

        if current_folder != module.params["folder"]:
            move_user(module, base_url, headers)
            msg_tokens.append("User was moved.")

        if attributes != {} and current_explicit_attributes != attributes:
            set_user_attributes(module, attributes, base_url, headers)
            msg_tokens.append("User attributes changed.")

        if len(msg_tokens) >= 1:
            exit_changed(module, " ".join(msg_tokens))
        else:
            exit_ok(module, "User already present. All explicit attributes as desired.")

    elif state == "present" and current_state == "absent":
        create_user(module, attributes, base_url, headers)
        exit_changed(module, "User created.")

    elif state == "absent" and current_state == "absent":
        exit_ok(module, "User already absent.")

    elif state == "absent" and current_state == "present":
        delete_user(module, base_url, headers)
        exit_changed(module, "User deleted.")

    else:
        exit_failed(module, "Unknown error")


def main():
    run_module()


if __name__ == "__main__":
    main()
