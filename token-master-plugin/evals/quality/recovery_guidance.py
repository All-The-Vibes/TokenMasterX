"""Explicit recovery namespaces for a shared comparator tool inventory.

Descriptions change equally in both arms; schemas, transformation rules and
recovery implementations do not. Never silently route one provider's reference
through another provider's store.
"""
import copy


def clarify_recovery_tools(tools):
    result = copy.deepcopy(tools)
    descriptions = {
        "retrieve_original": (
            "TokenMaster/Brainspace recovery only. For [[BR:...]] markers or their "
            "root/fragment IDs, use this tool with ref set to that reference and "
            "offset=0. It returns a 32768-character exact original page; follow "
            "next_offset until complete. Do not send TokenMaster references to headroom_retrieve."
        ),
        "search_original": (
            "Search a TokenMaster/Brainspace [[BR:...]] original or its root/fragment ID "
            "for exact text. This is not the Headroom recovery store."
        ),
        "headroom_retrieve": (
            "Headroom recovery only. Use the hash from Headroom markers such as "
            "[N words compressed ... Retrieve more: hash=...] or <<ccr:...>>. "
            "Do not use this for TokenMaster/Brainspace [[BR:...]] references; "
            "those belong to retrieve_original."
        ),
    }
    names = [tool.get("name") for tool in result]
    if any(names.count(name) != 1 for name in descriptions):
        raise ValueError("the declared recovery tools must each appear exactly once")
    for tool in result:
        if tool["name"] in descriptions:
            tool["description"] = descriptions[tool["name"]]
    return result


def absent_headroom_message():
    return {
        "error": "No Headroom reference exists in this arm.",
        "recovery_guidance": (
            "TokenMaster/Brainspace [[BR:...]] references and their IDs belong to "
            "retrieve_original(ref=the_reference, offset=0), not headroom_retrieve."
        ),
    }
