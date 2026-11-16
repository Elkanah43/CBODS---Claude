import re
import pathlib

classes = {}
order = []
for p in sorted(pathlib.Path('.').rglob('*.py')):
    s = str(p)
    if '.git' in s or 'node_modules' in s or 'venv' in s:
        continue
    txt = p.read_text(encoding='utf-8', errors='ignore')
    cur = None
    for line in txt.splitlines():
        m = re.match(r'class\s+(\w+)\(', line)
        if m:
            cur = m.group(1)
            if cur not in classes:
                classes[cur] = {'file': s.replace(chr(92), '/'), 'n': 0}
                order.append(cur)
            continue
        if cur and re.match(r'\s+def\s+test\w*\s*\(', line):
            classes[cur]['n'] += 1

tc = [c for c in order if c.endswith('Tests') and classes[c]['n'] > 0]
print('classes:', len(tc), 'methods:', sum(classes[c]['n'] for c in tc))
for c in tc:
    print('%-42s %3d  %s' % (c, classes[c]['n'], classes[c]['file']))
