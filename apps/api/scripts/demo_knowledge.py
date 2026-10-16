"""Additional fictional demo knowledge: varied topics and close lexical distractors."""

# key, title, body, calibration paraphrase. The -ar suffix selects Arabic metadata.
EXTRA_FAQS = (
    (
        "arrival",
        "Arrival preparation",
        "Arrive ten minutes before your confirmed visit to complete the intake form.",
        "How early should I arrive for my confirmed visit?",
    ),
    (
        "records",
        "Previous records",
        "Bring copies of previous dental records to your first visit.",
        "Should I bring my previous dental records?",
    ),
    (
        "access",
        "Step free entrance",
        "A step free ramp connects the main entrance to reception.",
        "Can I reach reception without using steps?",
    ),
    (
        "lift",
        "Building lift",
        "The building lift stops at the first floor demonstration room.",
        "Which floor does the building lift serve?",
    ),
    (
        "bicycle",
        "Bicycle rack",
        "A bicycle rack stands beside the blue side gate.",
        "Where can I leave my bicycle?",
    ),
    (
        "bus",
        "Bus stop",
        "The fictional Route Cedar bus stops at Example Square, two blocks from the clinic.",
        "Which bus stops near the clinic?",
    ),
    (
        "water",
        "Drinking water",
        "A drinking water dispenser is available beside reception.",
        "Where can I get drinking water while waiting?",
    ),
    (
        "wifi",
        "Guest wireless access",
        "Ask reception for a single visit guest WiFi access code.",
        "How do I obtain a guest wireless access code?",
    ),
    (
        "children",
        "Children waiting area",
        "The children's waiting area contains picture books and washable toys.",
        "What can children use in the waiting area?",
    ),
    (
        "companion",
        "Visit companion",
        "One adult companion may accompany a visitor to reception.",
        "May an adult companion come with me to reception?",
    ),
    (
        "interpreter",
        "Interpreter request",
        "Request an interpreter through the chat at least two weekdays before a visit.",
        "How far ahead should I request an interpreter?",
    ),
    (
        "feedback",
        "Visit feedback",
        "Submit visit feedback using the paper feedback box beside reception.",
        "Where should I submit feedback after a visit?",
    ),
    (
        "lost-property",
        "Lost property",
        "Reception keeps lost property in a labelled cabinet for fourteen days.",
        "How long does reception keep lost belongings?",
    ),
    (
        "receipts",
        "Duplicate receipts",
        "Request a duplicate demo receipt from reception using your visit reference.",
        "How can I obtain another copy of my demo receipt?",
    ),
    (
        "reminders",
        "Visit reminders",
        "Opt in to a visit reminder by asking the demo agent during confirmation.",
        "How do I opt in to a visit reminder?",
    ),
    (
        "reschedule",
        "Move a confirmed visit",
        "To move a confirmed visit, send your visit reference and preferred weekday in this chat.",
        "What information is needed to move my confirmed visit?",
    ),
    (
        "privacy",
        "Private discussion",
        "Ask reception for the quiet consultation desk for a private administrative discussion.",
        "Where can I discuss administration privately?",
    ),
    (
        "languages",
        "Reception languages",
        "The fictional reception team can discuss administrative questions in English and Arabic.",
        "Which languages can reception use for administrative questions?",
    ),
    (
        "forms",
        "Large print forms",
        "Large print intake forms are available on request at reception.",
        "Can reception provide a large print intake form?",
    ),
    (
        "guide",
        "Assistance animals",
        "Trained assistance animals may accompany visitors in the reception area.",
        "May a trained assistance animal enter reception?",
    ),
    (
        "delivery",
        "Courier deliveries",
        "Couriers leave office supply deliveries at the rear delivery desk.",
        "Where should couriers leave office supplies?",
    ),
    (
        "recruitment",
        "Recruitment enquiries",
        "Recruitment enquiries use the fictional careers form; reception does not collect resumes.",
        "Where should I send a recruitment enquiry?",
    ),
    (
        "workshop",
        "School workshop",
        "The fictional school workshop lasts forty minutes and covers brushing habits.",
        "How long is the school brushing workshop?",
    ),
    (
        "leaflets",
        "Information leaflets",
        "Printed information leaflets are available in English and Arabic at the leaflet stand.",
        "Which languages are available for printed information leaflets?",
    ),
    (
        "shop-hours",
        "Supply shop opening hours",
        (
            "The fictional supply shop is open Monday to Friday from 10:00 to 16:00; these "
            "are shop hours only."
        ),
        "When does the supply shop open on weekdays?",
    ),
    (
        "workshop-hours",
        "Workshop opening hours",
        "The brushing workshop opens Tuesday from 11:00 to 12:00; these are workshop hours only.",
        "What are the Tuesday brushing workshop hours?",
    ),
    (
        "shop-pricing",
        "Supply shop pricing",
        (
            "A fictional toothbrush costs 15 demo credits. Floss costs 20 demo credits at "
            "the supply shop."
        ),
        "How much is floss at the supply shop?",
    ),
    (
        "workshop-pricing",
        "Workshop pricing",
        "The school brushing workshop costs 30 demo credits per group, not per dental visit.",
        "What does the school workshop cost per group?",
    ),
    (
        "workshop-booking",
        "Workshop booking",
        (
            "Request a school workshop booking with the school form. A workshop coordinator "
            "confirms the group time."
        ),
        "Who confirms the school workshop group booking?",
    ),
    (
        "shop-booking",
        "Supply collection booking",
        (
            "Request a supply collection slot at the shop desk. A shop assistant confirms "
            "the collection time."
        ),
        "Who confirms a supply collection time?",
    ),
    (
        "shop-location",
        "Supply shop location",
        (
            "Find the fictional supply shop at 24 Example Lane, Demo City; this is not the "
            "clinic address."
        ),
        "What is the street number of the supply shop?",
    ),
    (
        "workshop-location",
        "School workshop location",
        (
            "Find the fictional school workshop at 42 Learning Lane, Demo City; this is not "
            "the clinic address."
        ),
        "Which street hosts the school workshop?",
    ),
    (
        "hours-ar",
        "مواعيد العيادة",
        "تفتح العيادة من الاثنين إلى الجمعة من الساعة التاسعة صباحا حتى الخامسة مساء.",
        "متى تفتح العيادة خلال أيام العمل؟",
    ),
    (
        "pricing-ar",
        "أسعار الكشف والتنظيف",
        "سعر الكشف خمسون رصيدا تجريبيا وسعر تنظيف الأسنان ثمانون رصيدا تجريبيا.",
        "ما سعر تنظيف الأسنان في العيادة؟",
    ),
    (
        "booking-ar",
        "حجز موعد بالعيادة",
        "اطلب حجز موعد في هذه المحادثة وسيؤكد الموظف التجريبي الوقت المناسب.",
        "كيف أطلب حجز موعد في العيادة؟",
    ),
    (
        "location-ar",
        "عنوان العيادة",
        "عنوان العيادة هو 42 شارع المثال في المدينة التجريبية.",
        "أين تقع العيادة وما عنوانها؟",
    ),
    (
        "arrival-ar",
        "الاستعداد للزيارة",
        "يرجى الحضور قبل الموعد المؤكد بعشر دقائق لملء استمارة الاستقبال.",
        "كم دقيقة أحضر قبل الموعد المؤكد؟",
    ),
    (
        "records-ar",
        "السجلات السابقة",
        "أحضر نسخة من سجلات الأسنان السابقة عند زيارتك الأولى.",
        "ماذا أحضر من سجلات عند الزيارة الأولى؟",
    ),
    (
        "shop-hours-ar",
        "مواعيد متجر المستلزمات",
        (
            "يفتح متجر المستلزمات من الاثنين إلى الجمعة من العاشرة صباحا حتى الرابعة مساء "
            "وهذه مواعيد المتجر فقط."
        ),
        "متى يفتح متجر المستلزمات خلال أيام العمل؟",
    ),
    (
        "shop-location-ar",
        "عنوان متجر المستلزمات",
        "عنوان متجر المستلزمات هو 24 شارع المثال في المدينة التجريبية وهذا ليس عنوان العيادة.",
        "ما عنوان متجر المستلزمات ورقم المبنى؟",
    ),
)
