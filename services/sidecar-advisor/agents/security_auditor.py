"""Security Auditor agent - reviews for hardcoded secrets, missing
auth checks, injection risks, unsafe deserialisation, missing input
sanitisation.

Why CodeLlama: Meta's original code-LLM has the strongest training-
data exposure to security-flavoured public repos (CVEs, OWASP test
cases, audit reports). The other 7B coders are stronger at pure
code-completion but weaker at "what's the vulnerability here".
"""
from .base import CoderAgent

AGENT = CoderAgent(
    name="security_auditor",
    role="author",
    model="codellama:7b-instruct",
    description="auth, secrets, OWASP injection, unsafe deserialisation",
    prompt_template=(
        "You are the Security Auditor. Review ONLY for security "
        "issues: hardcoded secrets, missing auth checks, injection "
        "(SQL / shell / template), unsafe deserialisation, missing "
        "input sanitisation. Focus ONLY on security - other "
        "reviewers cover correctness and tests. Reply with ONE "
        "paragraph.\n\n"
        "Code:\n{content}\n\nReview:"
    ),
)
