from datetime import datetime
import dateutil.parser

class LogEntry:
    def __init__(self, data):
        self.key = data['key']
        self.open = data['open']
        self.created_at = dateutil.parser.parse(data['created_at'])
        self.closed_at = dateutil.parser.parse(data['closed_at']) if not self.open else None
        self.channel_id = int(data['channel_id'])
        self.guild_id = int(data['guild_id'])
        self.creator = User(data['creator'])
        self.recipient = User(data['recipient'])
        self.closer = User(data['closer']) if not self.open else None
        self.messages = [Message(m) for m in data['messages']]

    def __str__(self):
        out = f"Thread created at {self.created_at.strftime('%d %b %Y - %H:%M UTC')}\n"

        if self.creator == self.recipient:
            out += f'[R] {self.creator} ({self.creator.id}) created a modmail thread. \n'
        else:
            out += f'[M] {self.creator} created a thread with [R] {self.recipient} ({self.recipient.id})\n'
        
        out += '────────────────' * 3 + '\n'

        if self.messages:
            for index, message in enumerate(self.messages):
                next_index = index + 1 if index + 1 < len(self.messages) else index
                curr, next = message.author, self.messages[next_index].author 

                author = curr
                base = message.created_at.strftime('%d/%m %H:%M') + (' [M] ' if author.mod else ' [R] ')
                base += f'{author}: {message.content}\n'
                for attachment in message.attachments:
                    base += 'Attachment: ' + attachment + '\n'
                    
                out += base

                if curr != next:
                    out += '────────────────' * 2 + '\n'
                    current_author = author

        if not self.open:
            if self.messages:  # only add if at least 1 message was sent
                out += '────────────────' * 3 + '\n'            
            out += f'[M] {self.closer} ({self.closer.id}) closed the modmail thread. \n'
            out += f"Thread closed at {self.closed_at.strftime('%d %b %Y - %H:%M UTC')} \n"
                    
        return out


class User:
    def __init__(self, data):
        self.id = int(data.get('id'))
        self.name = data['name']
        self.discriminator = data['discriminator']
        self.avatar_url = data['avatar_url']
        self.mod = data['mod']
    
    def __str__(self):
        return f'{self.name}#{self.discriminator}'
    
    def __eq__(self, other):
        return self.id == other.id and self.mod is other.mod


class Message:
    def __init__(self, data):
        self.id = int(data['message_id'])
        self.created_at = dateutil.parser.parse(data['timestamp'])
        self.content = data['content']
        self.attachments = data['attachments']
        self.author = User(data['author'])