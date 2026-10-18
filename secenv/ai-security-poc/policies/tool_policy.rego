# Deterministic tool-call policy for the secenv PoC agent.
#
# Queried by the agent's before_tool_call hook:
#   POST http://opa:8181/v1/data/secenv/tools/decision
#   {"input": {"tool": "...", "arguments": {...}, "context": {...}}}
#
# Deny by default: a tool is only allowed when it is on the allowlist AND no
# deny rule fires. Every deny carries a reason, which the agent writes to the
# immudb audit ledger together with the decision.
#
# Determinism: this policy uses no http.send, no time.*, no rand.*, no external
# data documents. The same input always yields the same decision, which is what
# makes the ledger entries reproducible and auditable after the fact.

package secenv.tools

import rego.v1

policy_version := "2026-10-17.2"

# --- Static configuration -----------------------------------------------------

allowed_tools := {"read_file", "list_dir", "http_get", "llm_chat"}

# Listed explicitly so an operator sees what is deliberately forbidden,
# rather than relying on absence from the allowlist alone.
denied_tools := {"shell_exec", "write_file", "delete_file", "docker", "ssh", "kubectl"}

file_tools := {"read_file", "list_dir"}

workspace_root := "/workspace"

# Only the gateway and the local MLX host may be contacted. Everything in
# secenv_internal has no egress anyway; this is the second line of defence.
egress_allowlist := {"llm-proxy", "host.docker.internal"}

max_payload_bytes := 65536

max_steps := 25

# --- Well-formed input --------------------------------------------------------
#
# Missing or mistyped context is a deny, not a pass. Otherwise an undefined
# comparison below would simply not fire and the call would slip through.

deny contains msg if {
	not input.tool
	msg := "no tool name supplied"
}

deny contains msg if {
	input.tool
	not is_string(input.tool)
	msg := "tool name must be a string"
}

# NOTE on the object.get form: `not is_number(input.context.step)` does NOT
# fire when the field is absent. An undefined operand makes the built-in call
# undefined, and the negated body then fails instead of succeeding — i.e. it
# fails open. Resolving the path to an explicit null default first is what
# makes the missing-field case an actual deny.
deny contains msg if {
	not is_number(object.get(input, ["context", "step"], null))
	msg := "context.step is missing or not a number"
}

deny contains msg if {
	not is_number(object.get(input, ["context", "payload_bytes"], null))
	msg := "context.payload_bytes is missing or not a number"
}

# --- Tool allowlist -----------------------------------------------------------

deny contains msg if {
	input.tool in denied_tools
	msg := sprintf("tool %q is explicitly denied", [input.tool])
}

deny contains msg if {
	is_string(input.tool)
	not input.tool in allowed_tools
	msg := sprintf("tool %q is not on the allowlist", [input.tool])
}

# --- File access --------------------------------------------------------------

deny contains msg if {
	input.tool in file_tools
	not input.arguments.path
	msg := "file tool called without a path argument"
}

deny contains msg if {
	input.tool in file_tools
	input.arguments.path
	not is_string(input.arguments.path)
	msg := "path argument must be a string"
}

# Containment is checked on a path-segment boundary. A plain startswith would
# accept "/workspace-evil/secrets", which is a sibling directory, not a child.
deny contains msg if {
	input.tool in file_tools
	p := input.arguments.path
	is_string(p)
	not path_within(p, workspace_root)
	msg := sprintf("path %q is outside %q", [p, workspace_root])
}

deny contains msg if {
	input.tool in file_tools
	p := input.arguments.path
	is_string(p)
	contains(p, "..")
	msg := sprintf("path %q contains a traversal segment", [p])
}

# --- Network access -----------------------------------------------------------

deny contains msg if {
	input.tool == "http_get"
	not is_string(object.get(input, ["arguments", "url"], null))
	msg := "http_get requires a string url argument"
}

deny contains msg if {
	input.tool == "http_get"
	url := object.get(input, ["arguments", "url"], "")
	is_string(url)
	not absolute_http_url(url)
	msg := "http_get requires an absolute http:// or https:// URL"
}

# request_host is undefined for anything that is not an absolute http(s) URL;
# that case is already covered by the rule above, so binding it here keeps this
# rule total without a second "unparseable" branch.
deny contains msg if {
	input.tool == "http_get"
	host := request_host
	not host in egress_allowlist
	msg := sprintf("host %q is not on the egress allowlist", [host])
}

# --- Cross-cutting limits -----------------------------------------------------

# Unmasked personal data must never leave the agent, whatever the tool.
# pii_masked is resolved with an explicit default so that *omitting* the flag
# counts as "not masked" rather than skipping the rule.
deny contains msg if {
	input.context.pii_detected == true
	object.get(input, ["context", "pii_masked"], false) != true
	msg := "payload contains unmasked PII"
}

# Oversized payloads are refused before they reach the model.
deny contains msg if {
	input.context.payload_bytes > max_payload_bytes
	msg := sprintf(
		"payload of %d bytes exceeds the limit of %d",
		[input.context.payload_bytes, max_payload_bytes],
	)
}

# Bounded run length — a looping agent is stopped by policy, not by luck.
deny contains msg if {
	input.context.step > max_steps
	msg := sprintf("step %d exceeds the limit of %d", [input.context.step, max_steps])
}

# --- Decision -----------------------------------------------------------------

default allow := false

allow if {
	input.tool in allowed_tools
	count(deny) == 0
}

decision := {
	"allow": allow,
	"reasons": sort([msg | some msg in deny]),
	"tool": object.get(input, "tool", null),
	"policy_version": policy_version,
}

# --- Helpers ------------------------------------------------------------------

# True when p is root itself or lies beneath it on a segment boundary.
path_within(p, root) if p == root

path_within(p, root) if startswith(p, concat("", [root, "/"]))

absolute_http_url(url) if startswith(lower(url), "http://")

absolute_http_url(url) if startswith(lower(url), "https://")

# Host part of the URL, without scheme, port, credentials or path. Undefined
# for anything that is not an absolute http(s) URL, which the deny rule above
# turns into a refusal.
request_host := host if {
	url := object.get(input.arguments, "url", "")
	is_string(url)
	absolute_http_url(url)
	stripped := replace(replace(lower(url), "https://", ""), "http://", "")
	authority := split(stripped, "/")[0]
	host := split(split(authority, "@")[count(split(authority, "@")) - 1], ":")[0]
}
