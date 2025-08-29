from django import forms

SOURCE_CHOICES = [
    ("openalex", "OpenAlex"),
    ("crossref", "Crossref"),
    ("arxiv", "arXiv"),
]

class SearchForm(forms.Form):
    name = forms.CharField(label="中文姓名", max_length=64)
    pinyin = forms.CharField(label="拼音覆盖（可选）", max_length=128, required=False)

    # ✅ 新增：单位关键词（支持中文/英文，模糊匹配）
    affiliation = forms.CharField(
        label="单位关键词（可选）",
        required=False,
        help_text="如：北京邮电大学 / Beijing University of Posts and Telecommunications"
    )

    # 如果你已把年份改成日期，这两项还是保留你当前版本
    start_date = forms.DateField(label="起始日期", required=False, widget=forms.DateInput(attrs={"type":"date"}))
    end_date   = forms.DateField(label="截止日期", required=False, widget=forms.DateInput(attrs={"type":"date"}))

    sources = forms.MultipleChoiceField(label="数据源", choices=SOURCE_CHOICES,
                                        initial=["openalex","crossref","arxiv"],
                                        widget=forms.CheckboxSelectMultiple)
    run_sync = forms.BooleanField(label="同步执行（调试用）", required=False)

    def clean(self):
        cleaned = super().clean()
        sd, ed = cleaned.get("start_date"), cleaned.get("end_date")
        if sd and ed and sd > ed:
            raise forms.ValidationError("起始日期不能晚于截止日期")
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
