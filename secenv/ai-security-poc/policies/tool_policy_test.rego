# Unit tests for the secenv tool-call policy.
#
#   opa test policies/ -v
#
# These run without Docker and without a network, which makes them the cheapest
# gate on the most security-critical component of the PoC. Every deny rule has
# at least one test, and the allow cases pin down what is deliberately permitted
# so a future widening of the policy shows up as a failing test.

package secenv.tools_test

import data.secenv.tools
import rego.v1

# A well-formed context; individual tests override what they care about.
base_context := {
	"step": 1,
	"run_id": "test",
	"payload_bytes": 128,
	"pii_detected": false,
	"pii_masked": false,
}

request(tool, arguments) := {
	"tool": tool,
	"arguments": arguments,
	"context": base_context,
}

with_context(tool, arguments, overrides) := {
	"tool": tool,
	"arguments": arguments,
	"context": object.union(base_context, overrides),
}

# --- Allowed paths ------------------------------------------------------------

test_read_inside_workspace_allowed if {
	tools.allow with input as request("read_file", {"path": "/workspace/notes.txt"})
}

test_workspace_root_itself_allowed if {
	tools.allow with input as request("list_dir", {"path": "/workspace"})
}

test_llm_chat_allowed if {
	tools.allow with input as request("llm_chat", {"prompt": "hello"})
}

test_http_get_to_gateway_allowed if {
	tools.allow with input as request("http_get", {"url": "http://llm-proxy:8080/v1/models"})
}

# --- Tool allowlist -----------------------------------------------------------

test_shell_exec_denied if {
	not tools.allow with input as request("shell_exec", {"command": "id"})
}

test_write_file_denied if {
	not tools.allow with input as request("write_file", {"path": "/workspace/x", "content": "y"})
}

test_unknown_tool_denied if {
	not tools.allow with input as request("exfiltrate", {})
}

test_missing_tool_denied if {
	not tools.allow with input as {"arguments": {}, "context": base_context}
}

test_non_string_tool_denied if {
	not tools.allow with input as request(42, {})
}

# --- Path containment ---------------------------------------------------------

test_absolute_path_outside_workspace_denied if {
	not tools.allow with input as request("read_file", {"path": "/etc/passwd"})
}

# Regression: a plain startswith check accepted this sibling directory.
test_sibling_directory_prefix_denied if {
	not tools.allow with input as request("read_file", {"path": "/workspace-evil/secrets"})
}

test_path_traversal_denied if {
	not tools.allow with input as request("read_file", {"path": "/workspace/../etc/shadow"})
}

test_embedded_traversal_denied if {
	not tools.allow with input as request("read_file", {"path": "/workspace/sub/../../etc/shadow"})
}

test_relative_path_denied if {
	not tools.allow with input as request("read_file", {"path": "workspace/notes.txt"})
}

test_missing_path_denied if {
	not tools.allow with input as request("read_file", {})
}

test_non_string_path_denied if {
	not tools.allow with input as request("read_file", {"path": 123})
}

# --- Network ------------------------------------------------------------------

test_unlisted_host_denied if {
	not tools.allow with input as request("http_get", {"url": "https://example.com/data"})
}

test_credential_prefix_cannot_spoof_host if {
	# urllib connects to the authority after "@", so the policy must judge that
	# host — not the decoy in front of it.
	not tools.allow with input as request("http_get", {"url": "https://llm-proxy@example.com/data"})
}

test_non_http_scheme_denied if {
	not tools.allow with input as request("http_get", {"url": "file:///etc/passwd"})
}

test_scheme_lookalike_denied if {
	not tools.allow with input as request("http_get", {"url": "httpfoo://llm-proxy/x"})
}

test_missing_url_denied if {
	not tools.allow with input as request("http_get", {})
}

test_non_string_url_denied if {
	not tools.allow with input as request("http_get", {"url": 7})
}

# --- Cross-cutting limits -----------------------------------------------------

test_unmasked_pii_denied if {
	not tools.allow with input as with_context(
		"read_file",
		{"path": "/workspace/notes.txt"},
		{"pii_detected": true, "pii_masked": false},
	)
}

test_masked_pii_allowed if {
	tools.allow with input as with_context(
		"llm_chat",
		{"prompt": "hi"},
		{"pii_detected": true, "pii_masked": true},
	)
}

test_oversized_payload_denied if {
	not tools.allow with input as with_context(
		"llm_chat",
		{"prompt": "hi"},
		{"payload_bytes": 65537},
	)
}

test_step_budget_exhausted_denied if {
	not tools.allow with input as with_context("llm_chat", {"prompt": "hi"}, {"step": 26})
}

test_last_step_within_budget_allowed if {
	tools.allow with input as with_context("llm_chat", {"prompt": "hi"}, {"step": 25})
}

# --- Malformed input fails closed ---------------------------------------------

test_missing_context_denied if {
	not tools.allow with input as {"tool": "llm_chat", "arguments": {"prompt": "hi"}}
}

test_non_numeric_step_denied if {
	not tools.allow with input as with_context("llm_chat", {"prompt": "hi"}, {"step": "one"})
}

test_missing_payload_bytes_denied if {
	not tools.allow with input as {
		"tool": "llm_chat",
		"arguments": {"prompt": "hi"},
		"context": {"step": 1},
	}
}

test_empty_input_denied if {
	not tools.allow with input as {}
}

# Regression: an omitted pii_masked flag must count as "not masked". Written as
# `not input.context.pii_masked == true` this rule silently did not fire.
test_pii_detected_without_masked_flag_denied if {
	not tools.allow with input as {
		"tool": "llm_chat",
		"arguments": {"prompt": "hi"},
		"context": {"step": 1, "payload_bytes": 10, "pii_detected": true},
	}
}

# Regression: http_get with no arguments object at all must still be denied.
test_http_get_without_arguments_denied if {
	not tools.allow with input as {
		"tool": "http_get",
		"context": {"step": 1, "payload_bytes": 10},
	}
}

test_file_tool_without_arguments_denied if {
	not tools.allow with input as {
		"tool": "read_file",
		"context": {"step": 1, "payload_bytes": 10},
	}
}

# --- Decision document shape --------------------------------------------------

test_decision_carries_reasons_on_deny if {
	d := tools.decision with input as request("shell_exec", {"command": "id"})
	d.allow == false
	count(d.reasons) > 0
	d.policy_version != ""
}

test_decision_has_no_reasons_on_allow if {
	d := tools.decision with input as request("llm_chat", {"prompt": "hi"})
	d.allow == true
	count(d.reasons) == 0
}
