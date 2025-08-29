from django.db import models

class AuthorProfile(models.Model):
    cn_name = models.CharField(max_length=64)
    orcid = models.CharField(max_length=32, blank=True, null=True, unique=True)
    affiliations = models.JSONField(default=list, blank=True)
    email_domains = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class SearchJob(models.Model):
    job_id = models.CharField(max_length=24, primary_key=True)
    hints = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, default="running")  # running/done/failed
    progress = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

class Paper(models.Model):
    title = models.TextField()
    year = models.IntegerField(null=True, blank=True)
    month = models.IntegerField(null=True, blank=True)              # 新增：出版月（1-12）
    venue = models.CharField(max_length=256, blank=True)
    doi = models.CharField(max_length=128, blank=True, null=True, unique=True)
    url = models.TextField(blank=True)
    source = models.CharField(max_length=32)  # openalex/crossref/arxiv/mock
    authors = models.JSONField(default=list, blank=True)            # 新增：作者全名列表（顺序）
    score = models.FloatField(default=0.0)                          # 保留旧字段，但我们不再显示/使用
    state = models.CharField(max_length=16, default="pending")
    task_ref = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
