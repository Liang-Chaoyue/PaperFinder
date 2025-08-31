from django import forms

SOURCE_CHOICES = [
    ("openalex", "OpenAlex"),
    ("crossref", "Crossref"),
    ("arxiv", "arXiv"),
    ("scholar", "Google Scholar (SerpAPI)"),
]

class SearchForm(forms.Form):
    # —— 单人检索（原有字段）——
    name = forms.CharField(label="中文姓名", max_length=64, required=False)  # 注意设为可选
    pinyin = forms.CharField(label="拼音覆盖（可选）", max_length=128, required=False)

    affiliation = forms.CharField(
        label="单位关键词（可选）",
        required=False,
        help_text="如：北京邮电大学 / Beijing University of Posts and Telecommunications"
    )

    start_date = forms.DateField(label="起始日期", required=False, widget=forms.DateInput(attrs={"type":"date"}))
    end_date   = forms.DateField(label="截止日期", required=False, widget=forms.DateInput(attrs={"type":"date"}))

    sources = forms.MultipleChoiceField(
        label="数据源",
        choices=SOURCE_CHOICES,
        initial=["openalex","crossref","arxiv"],
        widget=forms.CheckboxSelectMultiple
    )
    run_sync = forms.BooleanField(label="同步执行（调试用）", required=False)

    # —— 批量导入（新增）——
    names_text = forms.CharField(
        label="批量姓名（每行一个，逗号分隔：姓名[, 拼音][, 单位]）",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 6,
            "placeholder": "张三, zhang san, 北京邮电大学\n李四\n王五, wang wu"
        }),
        help_text="示例：张三, zhang san, 北京邮电大学；每行一条，拼音与单位可省略。"
    )
    names_file = forms.FileField(
        label="或上传 CSV/Excel",
        required=False,
        help_text="列名：name,pinyin,affiliation,start_date,end_date；编码默认 UTF-8，Excel 需 xlsx。"
    )

    # 批量的默认值（当某行未提供时使用）
    default_affiliation = forms.CharField(label="默认单位关键词（批量）", required=False)
    default_start_date  = forms.DateField(label="默认起始日期（批量）", required=False, widget=forms.DateInput(attrs={"type":"date"}))
    default_end_date    = forms.DateField(label="默认截止日期（批量）",   required=False, widget=forms.DateInput(attrs={"type":"date"}))

    def clean(self):
        cleaned = super().clean()
        sd, ed = cleaned.get("start_date"), cleaned.get("end_date")
        if sd and ed and sd > ed:
            raise forms.ValidationError("起始日期不能晚于截止日期")

        # 选择其一：单人 or 批量
        single = bool(cleaned.get("name"))
        bulk = bool(cleaned.get("names_text") or cleaned.get("names_file"))
        if not single and not bulk:
            raise forms.ValidationError("请填写单个姓名，或使用批量导入（文本/文件）之一。")
        if single and bulk:
            raise forms.ValidationError("单人检索与批量导入不可同时使用，请二选一。")

        return cleaned


class PaperFilterForm(forms.Form):
    job_id = forms.CharField(label="任务ID", required=False)
    q = forms.CharField(label="标题关键词", required=False)
    state = forms.ChoiceField(label="状态", required=False,
                              choices=[("", "全部"), ("pending","待定"), ("confirmed","已确认"), ("rejected","不相关")])
    source = forms.ChoiceField(label="来源", required=False,
                               choices=[("", "全部")] + SOURCE_CHOICES)
    year_from = forms.IntegerField(label="年份≥", required=False)
    year_to = forms.IntegerField(label="年份≤", required=False)
