from django import template

register = template.Library()

STATE_LABELS = {
    "pending": "待定",
    "confirmed": "已确认",
    "rejected": "不相关",
}
STATE_BADGE = {
    "pending": "secondary",
    "confirmed": "success",
    "rejected": "danger",
}

JOB_STATUS_LABELS = {
    "running": "进行中",
    "done": "完成",
    "failed": "失败",
}
JOB_STATUS_BADGE = {
    "running": "warning",
    "done": "success",
    "failed": "danger",
}

@register.filter
def state_cn(value: str):
    return STATE_LABELS.get((value or "").lower(), value)

@register.filter
def state_badge(value: str):
    return STATE_BADGE.get((value or "").lower(), "secondary")

@register.filter
def job_status_cn(value: str):
    return JOB_STATUS_LABELS.get((value or "").lower(), value)

@register.filter
def job_status_badge(value: str):
    return JOB_STATUS_BADGE.get((value or "").lower(), "secondary")
