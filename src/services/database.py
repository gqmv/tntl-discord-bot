from dataclasses import dataclass

import psycopg


class DatabaseService:
    def __init__(self, conn_string: str):
        self._connection_string = conn_string

    def get_connection(self):
        return psycopg.connect(self._connection_string)

    def migrate(self):
        with self.get_connection() as conn:
            print("Migrating database...")

            conn.execute(
                "CREATE TABLE IF NOT EXISTS tntl_channel (id BIGSERIAL PRIMARY KEY, discord_channel_id BIGINT NOT NULL UNIQUE, max_submissions INTEGER NOT NULL)"
            )

            conn.execute(
                "CREATE TABLE IF NOT EXISTS tntl_submission (id BIGSERIAL PRIMARY KEY, message_text TEXT NOT NULL, tntl_channel_id BIGINT NOT NULL REFERENCES tntl_channel(id) ON DELETE CASCADE, submitter_id BIGINT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

            conn.execute(
                "CREATE TABLE IF NOT EXISTS tntl_submission_message (id BIGSERIAL PRIMARY KEY, tntl_submission_id BIGINT NOT NULL REFERENCES tntl_submission(id) ON DELETE CASCADE, discord_message_id BIGINT NOT NULL, UNIQUE(tntl_submission_id))"
            )

            conn.execute(
                "CREATE TABLE IF NOT EXISTS tntl_message_upvote (id BIGSERIAL PRIMARY KEY, tntl_message_id BIGINT NOT NULL REFERENCES tntl_message(id) ON DELETE CASCADE, user_id BIGINT NOT NULL, UNIQUE(tntl_message_id, user_id))"
            )
            print("Database migrated.")

    def define_tntl_channel(self, discord_channel_id: int, max_submissions: int):
        print(
            f"Defining Try Not To Laugh channel with ID {discord_channel_id} and {max_submissions} submissions."
        )
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO tntl_channel (discord_channel_id, max_submissions) VALUES (%s, %s)",
                (discord_channel_id, max_submissions),
            )

    def get_tntl_channel_id(self, discord_channel_id: int) -> int | None:
        with self.get_connection() as conn:
            result = conn.execute(
                "SELECT id FROM tntl_channel WHERE discord_channel_id = %s",
                (discord_channel_id,),
            ).fetchone()
            return result[0] if result else None

    def check_tntl_message_exists(self, tntl_message_id: int) -> bool:
        with self.get_connection() as conn:
            return (
                conn.execute(
                    "SELECT COUNT(*) FROM tntl_submission WHERE id = %s",
                    (tntl_message_id,),
                ).fetchone()[0]
                > 0
            )

    def can_submit_tntl_message(self, tntl_channel_id: int, submitter_id: int) -> bool:
        with self.get_connection() as conn:
            max_submissions = conn.execute(
                "SELECT max_submissions FROM tntl_channel WHERE id = %s",
                (tntl_channel_id,),
            ).fetchone()[0]
            submission_count = conn.execute(
                "SELECT COUNT(*) FROM tntl_submission WHERE tntl_channel_id = %s AND submitter_id = %s",
                (tntl_channel_id, submitter_id),
            ).fetchone()[0]
            return submission_count < max_submissions

    def submit_tntl_message(
        self, message_text: str, tntl_channel_id: int, submitter_id: int
    ) -> int:
        with self.get_connection() as conn:
            return conn.execute(
                "INSERT INTO tntl_submission (message_text, tntl_channel_id, submitter_id) VALUES (%s, %s, %s) RETURNING id",
                (message_text, tntl_channel_id, submitter_id),
            ).fetchone()[0]

    def upvote_tntl_message(self, tntl_message_id: int, user_id: int):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO tntl_message_upvote (tntl_message_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (tntl_message_id, user_id),
            )

    @dataclass
    class TopUpvotedMessage:
        message_text: str
        upvote_count: int
        sender_id: int

    def get_top_upvoted_messages(
        self, tntl_channel_id: int, limit: int = 10
    ) -> list[TopUpvotedMessage]:
        with self.get_connection() as conn:
            result = conn.execute(
                """
                SELECT m.message_text, COUNT(u.user_id), m.submitter_id 
                FROM tntl_message m
                LEFT JOIN tntl_message_upvote u ON m.id = u.tntl_message_id
                WHERE m.tntl_channel_id = %s
                GROUP BY m.id, m.message_text, m.submitter_id
                ORDER BY COUNT(u.user_id) DESC 
                LIMIT %s
                """,
                (tntl_channel_id, limit),
            ).fetchall()

            return [
                self.TopUpvotedMessage(message_text, upvote_count, sender_id)
                for message_text, upvote_count, sender_id in result
            ]

    def get_top_upvoted_user_ids(
        self, tntl_channel_id: int, limit: int = 10
    ) -> list[int]:
        with self.get_connection() as conn:
            result = conn.execute(
                "SELECT user_id FROM tntl_message_upvote WHERE tntl_message_id IN (SELECT id FROM tntl_message WHERE tntl_channel_id = %s) GROUP BY user_id ORDER BY COUNT(tntl_message_id) DESC LIMIT %s",
                (tntl_channel_id, limit),
            ).fetchall()
            return [user_id for (user_id,) in result]

    def end_tntl_cycle(self, tntl_channel_id: int):
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM tntl_submission WHERE tntl_channel_id = %s",
                (tntl_channel_id,),
            )

    @dataclass
    class TntlSubmission:
        id: int
        message_text: str
        submitter_id: int

    def get_tntl_submissions(self, tntl_channel_id: int) -> list[TntlSubmission]:
        with self.get_connection() as conn:
            result = conn.execute(
                "SELECT id, message_text, submitter_id FROM tntl_submission WHERE tntl_channel_id = %s",
                (tntl_channel_id,),
            ).fetchall()
            return [
                self.TntlSubmission(id, message_text, submitter_id)
                for id, message_text, submitter_id in result
            ]

    def link_tntl_submission_to_discord_message(
        self, tntl_submission_id: int, discord_message_id: int
    ):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO tntl_submission_message (tntl_submission_id, discord_message_id) VALUES (%s, %s)",
                (tntl_submission_id, discord_message_id),
            )

    def get_discord_message_id_by_tntl_submission_id(
        self, tntl_submission_id: int
    ) -> int | None:
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT discord_message_id FROM tntl_submission_message WHERE tntl_submission_id = %s",
                (tntl_submission_id,),
            ).fetchone()[0]

    def get_upvote_count_by_tntl_submission_id(self, tntl_submission_id: int) -> int:
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM tntl_message_upvote WHERE tntl_message_id = %s",
                (tntl_submission_id,),
            ).fetchone()[0]

    def get_tntl_submission_ids(self) -> list[int]:
        with self.get_connection() as conn:
            result = conn.execute("SELECT id FROM tntl_submission").fetchall()
            return [id for (id,) in result]
