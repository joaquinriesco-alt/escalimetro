"""Secret scan E11 — separa NOMBRE de variable de VALOR de credencial. Nunca imprime valores."""
import os, re, subprocess, sys

# Patrones de VALOR (no de nombre). Un nombre suelto no es un hallazgo.
VALUE_PATTERNS = [
    ("openai_key",    re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("bearer",        re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}")),
    ("github_pat",    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws_key",       re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key",   re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("assigned_key",  re.compile(r"(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|API_KEY|SECRET|TOKEN)\s*[=:][ \t]*"
                                 r"['\"]?[A-Za-z0-9_\-]{16,}")),
]
TEXT_EXT = {".py",".md",".txt",".json",".toml",".cfg",".ini",".yml",".yaml",".sh",".html",".svg",
            ".example",".gitignore",".ipynb",".log",""}

files = subprocess.run(["git","ls-files","--cached","--others","--exclude-standard"],
                       capture_output=True, text=True).stdout.split("\n")
files = [f for f in files if f]
hits, scanned = [], 0
for f in files:
    if not os.path.isfile(f):
        continue
    if os.path.splitext(f)[1].lower() not in TEXT_EXT:
        continue
    if os.path.getsize(f) > 6_000_000:
        continue
    try:
        txt = open(f, encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    scanned += 1
    for i, line in enumerate(txt.splitlines(), 1):
        for kind, pat in VALUE_PATTERNS:
            if pat.search(line):
                hits.append((kind, f, i))
print(f"archivos candidatos a commit: {len(files)}")
print(f"archivos de texto escaneados: {scanned}")
print(f"patrones de VALOR buscados:   {len(VALUE_PATTERNS)}")
if hits:
    print("\nSECRET FOUND:")
    for kind, f, i in hits:
        print(f"  tipo={kind}  archivo={f}  linea~{i}")
    sys.exit(1)
print("\nSECRET SCAN: CLEAN — ningún valor de credencial en archivos a commitear")
