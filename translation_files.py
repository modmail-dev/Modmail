import json
import glob
import re
import string

data = {}
all_identifiers = []
identifiers = {}

class FormatError(Exception):
    def __init__(self, reason, string):
        super().__init__(f'Unable to parse {reason}: {string}')


for filename in glob.glob('**/*.py') + glob.glob('*.py'):
    if filename == 'translation_files.py':
        continue
    with open(filename, encoding='utf8') as f:
        filedata = f.read()
    regex_matches = re.findall(r'(?:^|[^A-z])_\(.+?(?:\'|\")\)+?', filedata, flags=re.DOTALL | re.MULTILINE)

    for i in regex_matches:
        if "f'" in i or 'f"' in i:
            print(FormatError('f-string', i))
        identifier = ''
        read = False
        ignore_inverted = False
        newline = False
        counter = 0
        mode = None
        for n in range(len(i)):
            triggered = False
            x = i[n]

            if x in ("'", '"') and not ignore_inverted:
                if not mode:
                    mode = x
                if mode == x:
                    read = not read
                    triggered = True

            if x == '\n':
                newline = True

            if read and not triggered:
                newline = False
                identifier += x

            if newline and x not in string.whitespace:
                counter += 1
                if counter > 1:
                    break
            else:
                counter = 0

            if x == '\\':
                ignore_inverted = True
            elif ignore_inverted:
                ignore_inverted = False

        data[identifier] = identifier
    print(filename)

with open('languages/en.json', 'w+') as f:
    json.dump(data, f, indent=4)
