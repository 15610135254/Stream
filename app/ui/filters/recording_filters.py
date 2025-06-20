from ...models.recording_status_model import RecordingStatus


class RecordingFilters:

    ERROR_STATUSES = [RecordingStatus.RECORDING_ERROR, RecordingStatus.LIVE_STATUS_CHECK_ERROR]

    STATUS_FILTER_MAP = {
        "all": lambda rec: True,
        "recording": lambda rec: rec.is_recording,
        "error": lambda rec: rec.status_info in RecordingFilters.ERROR_STATUSES,
        "offline": lambda rec: (
            not rec.is_live
            and rec.monitor_status
            and rec.status_info not in RecordingFilters.ERROR_STATUSES
        ),
        "stopped": lambda rec: not rec.monitor_status,
    }

    @classmethod
    def get_status_filter_result(cls, recording, filter_type) -> bool:

        filter_func = cls.STATUS_FILTER_MAP.get(
            filter_type,
            lambda _: False
        )
        return filter_func(recording)

    @classmethod
    def get_platform_filter_result(cls, recording, platform_filter) -> bool:
        return platform_filter in ("all", recording.platform_key)

    @classmethod
    def should_show_recording(cls, filter_type, platform_filter, recording) -> bool:
        status_visible = cls.get_status_filter_result(recording, filter_type)
        platform_visible = cls.get_platform_filter_result(recording, platform_filter)
        return status_visible and platform_visible
