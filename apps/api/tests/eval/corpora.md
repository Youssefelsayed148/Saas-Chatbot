# Evaluation corpora (P3-05) — fixture files ingested per eval bot

## EN services (ingested as a markdown page)

```markdown
---
title: Opening hours
source_url: https://eval.example.com/hours
language: en
page_type: faq
---
# Opening hours

We are open Monday to Friday from 9:00 to 17:00. On Saturdays the showroom
opens at 10:00 and closes at 14:00. The support chat uses the same schedule.
```

## EN returns policy

```markdown
---
title: Return policy
source_url: https://eval.example.com/returns
language: en
page_type: policy
---
# Return policy

Products can be returned within 14 days of delivery with the original
invoice. Personalised items are excluded unless the item is faulty.
```

## AR FAQ

```markdown
---
title: الأسئلة الشائعة
source_url: https://eval.example.com/ar/faq
language: ar
page_type: faq
---
# الأسئلة الشائعة

## ساعات العمل

نحن نعمل من الأحد إلى الخميس من الساعة ٩ صباحاً حتى ٥ مساءً.

## سياسة الاسترجاع

يمكن استرجاع المنتجات خلال ١٤ يومًا من الاستلام بشرط الاحتفاظ بالفاتورة.
```

## The unanswerable content hole (intentional)

No document mentions opening hours on **Sundays**, warranty terms, or
delivery to other countries — questions about those must be abstained.
