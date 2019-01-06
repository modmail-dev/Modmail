from collections import defaultdict
import re 

class Version:
    def __init__(self, version, lines):
        self.version = version
        self.lines = [x for x in lines.splitlines() if x]
        self.fields = defaultdict(str)
        self.description = ''
        self.parse()
    
    def __repr__(self):
        return f'Version({self.version}, description="{self.description}")'
    
    def parse(self):
        curr_action = None 
        for line in self.lines:
            if line.startswith('### '):
                curr_action = line.split('### ')[1]
            elif curr_action is None:
                self.description += line + '\n'
            else:
                self.fields[curr_action] += line + '\n'
        
class ChangeLogParser:
    regex = re.compile(r'# (v\d\.\d\.\d)([\S\s]*?(?=# v))')

    def __init__(self, text):
        self.text = text 
        self.versions = [Version(*m) for m in self.regex.findall(text)]

    @property
    def latest_version(self):
        return self.versions[0]
    

if __name__ == '__main__':
    with open('../CHANGELOG.md') as f:
        changelog = ChangeLogParser(f.read())
        print(changelog.latest_version)
