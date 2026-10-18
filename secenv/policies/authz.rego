package secenv.authz

import rego.v1

default decision := {"allow": false, "needs_approval": false, "reason": "default deny"}

in_task if {
	input.action in input.task.actions
	path_ok
	target_ok
	tool_ok
}

path_ok if {
	input.action != "read_file"
}

path_ok if {
	input.action == "read_file"
	input.path in input.task.paths
	not contains(input.path, "..")
}

target_ok if {
	input.action != "call_agent"
}

target_ok if {
	input.action == "call_agent"
	input.target in input.task.targets
	input.delegate == ""
}

tool_ok if {
	input.action != "mcp_call"
}

tool_ok if {
	input.action == "mcp_call"
	input.tool in input.task.tools
}

decision := {"allow": false, "needs_approval": false, "reason": "shell denied"} if {
	input.action == "shell"
}

decision := {"allow": false, "needs_approval": false, "reason": "delegate not allowed"} if {
	input.action == "call_agent"
	input.delegate != ""
}

decision := {"allow": false, "needs_approval": false, "reason": "outside task"} if {
	input.action != "shell"
	input.delegate == ""
	not in_task
}

decision := {"allow": false, "needs_approval": false, "reason": "llm url not allowed"} if {
	in_task
	input.action == "llm_chat"
	input.url != ""
}

decision := {"allow": false, "needs_approval": true, "reason": "egress needs approval"} if {
	in_task
	input.action == "egress"
}

decision := {"allow": true, "needs_approval": false, "reason": "within task"} if {
	in_task
	input.action != "egress"
	input.action != "shell"
	not llm_redirect
}

llm_redirect if {
	input.action == "llm_chat"
	input.url != ""
}
