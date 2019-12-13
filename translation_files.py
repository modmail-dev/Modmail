import csv
import glob
import re
import string

data = [('Identifier', 'English', 'Context')]
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

        all_identifiers.append(identifier)

        filedata_lines = filedata.splitlines()
        fullline = list(filter((lambda x: x.find(i.splitlines()[0]) != -1), filedata_lines))[0]
        count = 0
        for nline, line in enumerate(filedata_lines):
            if line == fullline:
                count += 1
                if count == all_identifiers.count(identifier):
                    linenum = nline + 1
                    break

        if identifier in identifiers.keys():
            if filename not in data[identifiers[identifier]][2]:
                data[identifiers[identifier]][2] += f' {filename}/L{linenum}'
            elif str(linenum) not in data[identifiers[identifier]][2]:
                split_space = data[identifiers[identifier]][2].split(' ')
                for nx, x in enumerate(split_space):
                    if filename in x:
                        split_space[nx] += f'/L{linenum}'
                        break
                data[identifiers[identifier]][2] = (' ').join(split_space)
        else:
            data.append([identifier, identifier, f'File: {filename}/L{linenum}'])
            identifiers[identifier] = len(data) - 1

    print(filename)

with open('languages/en.csv', 'w+') as f:
    csv.writer(f, dialect='unix').writerows(data)
