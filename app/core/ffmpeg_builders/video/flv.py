from ..base import FFmpegCommandBuilder


class FLVCommandBuilder(FFmpegCommandBuilder):
    def build_command(self) -> list[str]:
        command = self._get_basic_ffmpeg_command()
        additional_commands = [
            "-map", "0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-f", "flv",
            self.full_path,
        ]
        command.extend(additional_commands)
        return command
