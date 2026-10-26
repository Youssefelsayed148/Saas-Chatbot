# Frozen demo corpus (NileCart)

Issue #30. This is the document set the owner ingested for manual testing: the
ten `*_1.pdf` files (five policies, each in English and Arabic, four pages
each: 40 pages in total). It is the fixed input of the Nile evaluation
(`../nile_eval.jsonl`) and of the gate calibration tooling. **Do not edit,
re-export or replace these files**; the cases cite exact pages, and the hashes
below are verified by `tests/eval/offline/test_nile_eval_cases.py`.

Origin: copied byte for byte from `C:\Users\Youssef\Downloads\` on 2026-10-22
(files named `NN-topic-xx_1.pdf`). The un-suffixed twins (`NN-topic-xx.pdf`)
are a different, older export and are deliberately not part of this corpus.

Store in the documents: NileCart (Arabic: نايل كارت), policy version 2.4,
effective 1 October 2026. The store name appears on every page, which makes it a
useful trap for the retrieval gate (a question that only shares the store name
must not be treated as grounded).

| File | Topic | Pages |
|---|---|---|
| 01-shipping-en_1.pdf / 01-shipping-ar_1.pdf | Zones, fees, free-shipping thresholds, carrier, cut-off, tracking | 4 |
| 02-delivery-en_1.pdf / 02-delivery-ar_1.pdf | Delivery times, failed attempts, cash on delivery, inspection and damage | 4 |
| 03-terms-en_1.pdf / 03-terms-ar_1.pdf | Account rules, pricing, payment and cancellation, liability, privacy, law | 4 |
| 04-returns-en_1.pdf / 04-returns-ar_1.pdf | Return window, eligibility, return shipping costs, how to return | 4 |
| 05-refund-en_1.pdf / 05-refund-ar_1.pdf | Refund methods and timing, partial refunds, timeline, late refunds | 4 |

Text extraction (pypdf, the same library as the ingestion pipeline) returns
real, selectable text. Arabic comes out in Arabic presentation forms (visual
glyph variants) with Latin runs and digits placed visually; NFKC normalisation
restores the base letters, which the ingestion pipeline's text normaliser also
does. Digits and Latin e-mail addresses are reliable anchors for checks.

`SHA256SUMS.txt` lists the SHA-256 of each file (`sha256sum -c SHA256SUMS.txt`).
