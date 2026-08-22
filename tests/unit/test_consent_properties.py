from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from artek_buddy.consent import owner_command_is_readonly

# Modest bounds so backend stays inside pytest-timeout=60s.
bounded = settings(max_examples=40, deadline=400)

# Verbs the classifier must never treat as explore-only. Not `find`/`git`:
# those have readonly uses; write forms have their own properties.
WRITE_HEADS = (
    "rm",
    "mv",
    "cp",
    "chmod",
    "chown",
    "dd",
    "sudo",
    "bash",
    "sh",
    "python",
    "python3",
    "perl",
    "ruby",
    "node",
    "curl",
    "wget",
    "ssh",
    "tee",
    "install",
    "touch",
    "mkdir",
    "kill",
    "xargs",
    "sed",
    "awk",
    "apt-get",
    "pip",
    "npm",
)
WRITE_PREFIXES = ("", "/bin/", "/usr/bin/", "./")
GIT_WRITE = (
    "commit",
    "push",
    "add",
    "reset",
    "checkout",
    "merge",
    "rebase",
    "tag",
    "stash",
    "cherry-pick",
    "revert",
    "clean",
    "rm",
    "mv",
)
FIND_WRITE = ("-exec", "-execdir", "-ok", "-okdir", "-delete")
PIPE_SINKS = ("xargs rm", "tee out", "dd of=out")
REST = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 ._-",
    max_size=24,
)


def test_named_classifier_bug_find_exec_is_never_readonly() -> None:
    """Would be True if `find` were blindly readonly. Hypothesis shrinks here."""
    assert owner_command_is_readonly("find . -exec rm {} ;") is False


def test_timeout_wrapper_cannot_hide_rm() -> None:
    assert owner_command_is_readonly("timeout 1 rm -rf /tmp/x") is False


def test_pipeline_and_nested_shell_are_never_readonly() -> None:
    assert owner_command_is_readonly("ls | xargs rm") is False
    assert owner_command_is_readonly("bash -c 'rm -rf /'") is False
    assert owner_command_is_readonly("ls; rm -rf ~") is False


@bounded
@given(st.sampled_from(WRITE_PREFIXES), st.sampled_from(WRITE_HEADS), REST)
def test_write_heads_are_never_readonly(prefix: str, verb: str, rest: str) -> None:
    command = f"{prefix}{verb} {rest}".strip()
    assert owner_command_is_readonly(command) is False


@bounded
@given(st.sampled_from(WRITE_HEADS))
def test_wrappers_cannot_make_a_write_readonly(verb: str) -> None:
    assert owner_command_is_readonly(f"timeout 1 {verb} x") is False
    assert owner_command_is_readonly(f"nice {verb} x") is False
    assert owner_command_is_readonly(f"nohup {verb} x") is False
    assert owner_command_is_readonly(f"command {verb} x") is False
    assert owner_command_is_readonly(f"env {verb} x") is False


@bounded
@given(st.sampled_from(FIND_WRITE))
def test_find_write_flags_are_never_readonly(flag: str) -> None:
    command = "find . -delete" if flag == "-delete" else f"find . {flag} rm {{}} ;"
    assert owner_command_is_readonly(command) is False


@bounded
@given(st.sampled_from(GIT_WRITE))
def test_git_write_subcommands_are_never_readonly(sub: str) -> None:
    assert owner_command_is_readonly(f"git {sub}") is False


@bounded
@given(
    st.sampled_from(("ls", "cat", "echo", "git status")),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12),
)
def test_redirects_are_never_readonly(command: str, dest: str) -> None:
    assert owner_command_is_readonly(f"{command} > {dest}") is False


@bounded
@given(st.sampled_from(("ls", "cat f", "echo hi")), st.sampled_from(PIPE_SINKS))
def test_pipe_to_write_is_never_readonly(left: str, right: str) -> None:
    assert owner_command_is_readonly(f"{left} | {right}") is False


@bounded
@given(st.sampled_from(("rm -rf /", "touch x", "chmod 777 x")))
def test_command_substitution_is_never_readonly(inner: str) -> None:
    assert owner_command_is_readonly(f"echo $({inner})") is False
    assert owner_command_is_readonly(f"echo `{inner}`") is False
