"""initial create

Revision ID: ed42f95bfa77
Revises: 
Create Date: 2020-08-04 18:17:57.437436

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.expression import text

# revision identifiers, used by Alembic.
revision = "ed42f95bfa77"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "config",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("twitch_url", sa.Text, nullable=True, default=None),
        sa.Column("main_category_id", sa.String(24), nullable=True, default=None),
        sa.Column("fallback_category_id", sa.String(24), nullable=True, default=None),
        sa.Column("prefix", sa.String(2048), nullable=True, default=None),
        sa.Column("mention", sa.String(2048), nullable=True, default=None),
        sa.Column("main_color", sa.String(7), nullable=True, default=None),
        sa.Column("error_color", sa.String(7), nullable=True, default=None),
        sa.Column("user_typing", sa.Boolean, nullable=True, default=None),
        sa.Column("mod_typing", sa.Boolean, nullable=True, default=None),
        sa.Column("account_age", sa.Text, nullable=True, default=None),
        sa.Column("guild_age", sa.Text, nullable=True, default=None),
        sa.Column("thread_cooldown", sa.Text, nullable=True, default=None),
        sa.Column("reply_without_command", sa.Boolean, nullable=True, default=None),
        sa.Column("anon_reply_without_command", sa.Boolean, nullable=True, default=None),
        sa.Column("log_channel_id", sa.String(24), nullable=True, default=None),
        sa.Column("sent_emoji", sa.String(340), nullable=True, default=None),
        sa.Column("blocked_emoji", sa.String(340), nullable=True, default=None),
        sa.Column("close_emoji", sa.String(340), nullable=True, default=None),
        sa.Column("recipient_thread_close", sa.Boolean, nullable=True, default=None),
        sa.Column("thread_auto_close_silently", sa.Boolean, nullable=True, default=None),
        sa.Column("thread_auto_close", sa.Text, nullable=True, default=None),
        sa.Column("thread_auto_close_response", sa.String(2048), nullable=True, default=None),
        sa.Column("thread_creation_response", sa.String(2048), nullable=True, default=None),
        sa.Column("thread_creation_footer", sa.String(2048), nullable=True, default=None),
        sa.Column(
            "thread_self_closable_creation_footer", sa.String(2048), nullable=True, default=None
        ),
        sa.Column("thread_creation_title", sa.String(256), nullable=True, default=None),
        sa.Column("thread_close_footer", sa.String(2048), nullable=True, default=None),
        sa.Column("thread_close_title", sa.String(256), nullable=True, default=None),
        sa.Column("thread_close_response", sa.String(2048), nullable=True, default=None),
        sa.Column("thread_self_close_response", sa.String(2048), nullable=True, default=None),
        sa.Column("thread_move_notify", sa.Boolean, nullable=True, default=None),
        sa.Column("thread_move_response", sa.String(2048), nullable=True, default=None),
        sa.Column("disabled_new_thread_title", sa.String(256), nullable=True, default=None),
        sa.Column("disabled_new_thread_response", sa.String(2048), nullable=True, default=None),
        sa.Column("disabled_new_thread_footer", sa.String(2048), nullable=True, default=None),
        sa.Column("disabled_current_thread_title", sa.String(256), nullable=True, default=None),
        sa.Column(
            "disabled_current_thread_response", sa.String(2048), nullable=True, default=None
        ),
        sa.Column("disabled_current_thread_footer", sa.String(2048), nullable=True, default=None),
        sa.Column("recipient_color", sa.String(7), nullable=True, default=None),
        sa.Column("mod_color", sa.String(7), nullable=True, default=None),
        sa.Column("mod_tag", sa.String(2048), nullable=True, default=None),
        sa.Column("anon_username", sa.String(256), nullable=True, default=None),
        sa.Column("anon_avatar_url", sa.Text, nullable=True, default=None),
        sa.Column("anon_tag", sa.String(2048), nullable=True, default=None),
        sa.Column("activity_message", sa.String(128), nullable=True, default=None),
        sa.Column("activity_type", sa.SmallInteger, nullable=True, default=None),
        sa.Column("status", sa.String(12), nullable=True, default=None),
        sa.Column("dm_disabled", sa.SmallInteger, nullable=True, default=None),
        sa.Column("oauth_whitelist", sa.Text, nullable=True, default=None),
        sa.Column("blocked", sa.Text, nullable=True, default=None),
        sa.Column("blocked_whitelist", sa.Text, nullable=True, default=None),
        sa.Column("command_permissions", sa.Text, nullable=True, default=None),
        sa.Column("level_permissions", sa.Text, nullable=True, default=None),
        sa.Column("override_command_level", sa.Text, nullable=True, default=None),
        sa.Column("snippets", sa.Text, nullable=True, default=None),
        sa.Column("notification_squad", sa.Text, nullable=True, default=None),
        sa.Column("subscriptions", sa.Text, nullable=True, default=None),
        sa.Column("closures", sa.Text, nullable=True, default=None),
        sa.Column("plugins", sa.Text, nullable=True, default=None),
        sa.Column("aliases", sa.Text, nullable=True, default=None),
    )

    op.create_table(
        "logs_user",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("name", sa.String(32)),
        sa.Column("discriminator", sa.String(4)),
        sa.Column("avatar_url", sa.String(120)),
    )
    op.create_index("idx_user_name", "logs_user", ["name"])

    op.create_table(
        "logs",
        sa.Column("key", sa.String(16), primary_key=True),
        sa.Column("bot_id", sa.String(24), nullable=True),
        sa.Column("open", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime),
        sa.Column("closed_at", sa.DateTime, default=None, nullable=True),
        sa.Column("channel_id", sa.String(24), unique=True),
        sa.Column("guild_id", sa.String(24)),
        sa.Column("recipient_id", sa.String(24)),
        sa.Column("creator_id", sa.String(24)),
        sa.Column("creator_mod", sa.Boolean),
        sa.Column("closer_id", sa.String(24), default=None, nullable=True),
        sa.Column("close_message", sa.Text, default=None, nullable=True),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["config.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["creator_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["closer_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
    )

    op.create_index("idx_logs_bot_id", "logs", ["bot_id"])
    op.create_index("idx_logs_open", "logs", ["open"])
    op.create_index("idx_logs_closed", "logs", [text("closed_at DESC"), "closer_id"])
    op.create_index(
        "idx_logs_create", "logs", [text("created_at DESC"), "creator_id", "creator_mod"]
    )
    op.create_index("idx_logs_recipient", "logs", ["recipient_id", "bot_id"])
    op.create_index("idx_logs_channel", "logs", ["channel_id", "bot_id"])

    op.create_table(
        "logs_message",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("bot_id", sa.String(24), nullable=True),
        sa.Column("timestamp", sa.DateTime),
        sa.Column("author_id", sa.String(24)),
        sa.Column("author_mod", sa.Boolean),
        sa.Column("content", sa.String(2048)),
        sa.Column("type", sa.String(20), default="thread_message"),
        sa.Column("edited", sa.Boolean, default=False, server_default=text("FALSE")),
        sa.Column("deleted", sa.Boolean, default=False, server_default=text("FALSE")),
        sa.Column("log_key", sa.String(16)),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["config.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["log_key"], ["logs.key"], onupdate="CASCADE", ondelete="CASCADE"),
    )
    op.create_index("idx_message_bot_id", "logs_message", ["bot_id"])
    op.create_index("idx_message_log_key", "logs_message", ["log_key"])
    op.create_index("idx_message_timestamp", "logs_message", [text("timestamp DESC")])
    op.create_index("idx_message_author", "logs_message", ["author_id", "author_mod", "type"])
    op.create_index("idx_message_content", "logs_message", ["content", "bot_id"])

    op.create_table(
        "logs_attachment",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("filename", sa.String(32), server_default="uploaded_file"),
        sa.Column("is_image", sa.Boolean, server_default=text("TRUE")),
        sa.Column("size", sa.Integer, server_default=text("-1")),
        sa.Column("url", sa.String(340)),
        sa.Column("message_id", sa.String(24)),
        sa.Column("sender_id", sa.String(24)),
        sa.ForeignKeyConstraint(
            ["message_id"], ["logs_message.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
    )
    op.create_index("idx_attachment_message_id", "logs_attachment", ["message_id"])
    op.create_index("idx_attachment_sender_id", "logs_attachment", ["sender_id"])


def downgrade():
    op.drop_table("logs_attachment")
    op.drop_table("logs_message")
    op.drop_table("logs")
    op.drop_table("logs_user")
    op.drop_table("config")
