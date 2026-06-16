from app.models import Business, BusinessType, FaqEntry, ResponseStyle

# Marker the model must emit (verbatim) when it cannot answer from the business's
# own knowledge. ai_service detects it, escalates to the owner, and replaces the
# customer-facing reply. Keep in sync with NEED_HUMAN_MARKER in ai_service.
NEED_HUMAN_MARKER = "[NEED_HUMAN]"

_STYLE_INSTRUCTIONS = {
    ResponseStyle.FRIENDLY: "با لحنی دوستانه، صمیمی و گرم صحبت کن.",
    ResponseStyle.FORMAL: "با لحنی رسمی و حرفه‌ای صحبت کن.",
    ResponseStyle.BRIEF: "پاسخ‌ها را کوتاه و مختصر نگه دار، حداکثر ۲-۳ جمله.",
}


def _faq_section(faq: list[FaqEntry]) -> str:
    """Render owner-defined Q&A as the agent's source of truth, plus the rule for
    escalating questions it can't answer."""
    if faq:
        pairs = "\n".join(f"- سوال: {e.question}\n  جواب: {e.answer}" for e in faq)
        faq_block = f"سوال‌های متداول و پاسخ‌های تأییدشده توسط کسب‌وکار:\n{pairs}"
    else:
        faq_block = "هنوز سوال متداولی توسط کسب‌وکار ثبت نشده است."

    return f"""
        {faq_block}

        قانون مهم:
        - فقط بر اساس اطلاعات بالا (مشخصات کسب‌وکار و سوال‌های متداول) جواب بده.
        - اگر پاسخ سوال مشتری در این اطلاعات نبود، حدس نزن و چیزی از خودت نساز.
          در آن صورت دقیقاً و فقط همین نشانه را خروجی بده: {NEED_HUMAN_MARKER}
          (بدون هیچ متن اضافه‌ای). سوال به صاحب کسب‌وکار ارجاع داده می‌شود.
    """


def get_system_prompt(
    business: Business, details: dict[str, str], faq: list[FaqEntry] | None = None
) -> str:
    style = _STYLE_INSTRUCTIONS.get(business.response_style, _STYLE_INSTRUCTIONS[ResponseStyle.FRIENDLY])

    if business.type == BusinessType.SHOP:
        base = f"""
        تو دستیار فروش {business.name} هستی.
        حوزه کاری: {business.field}
        محصولات: {details.get('products', 'نامشخص')}
        ساعت کاری: {business.working_hours}
        تماس: {business.contact}
        سیاست بازگشت: {details.get('return_policy', 'نامشخص')}

        وظایف تو:
        - کمک به انتخاب محصول مناسب
        - پرسیدن نیاز و بودجه مشتری
        - پیشنهاد محصول بر اساس نیاز
        - اطلاع‌رسانی درباره گارانتی و بازگشت کالا

        {style}
        فقط به فارسی جواب بده.
        فقط درباره محصولات این فروشگاه صحبت کن.
        """

    elif business.type == BusinessType.EDUCATION:
        base = f"""
        تو مشاور آموزشی {business.name} هستی.
        حوزه کاری: {business.field}
        دوره‌ها: {details.get('courses', 'نامشخص')}
        ساعت کاری: {business.working_hours}
        تماس: {business.contact}
        رده سنی: {details.get('age_range', 'نامشخص')}

        وظایف تو:
        - راهنمایی برای انتخاب دوره مناسب
        - پرسیدن سطح و هدف یادگیری
        - معرفی دوره‌ها و سرفصل‌ها
        - اطلاع‌رسانی درباره شهریه و زمان‌بندی

        {style}
        فقط به فارسی جواب بده.
        فقط درباره دوره‌های این آموزشگاه صحبت کن.
        """

    elif business.type == BusinessType.SERVICE:
        base = f"""
        تو اپراتور پشتیبانی {business.name} هستی.
        حوزه کاری: {business.field}
        خدمات: {details.get('services', 'نامشخص')}
        ساعت کاری: {business.working_hours}
        تماس: {business.contact}
        منطقه خدمات: {details.get('service_area', 'نامشخص')}

        وظایف تو:
        - ثبت درخواست خدمات
        - پرسیدن آدرس و زمان مناسب مشتری
        - اطلاع‌رسانی درباره قیمت و زمان‌بندی
        - هماهنگی برای ارسال تیم

        {style}
        فقط به فارسی جواب بده.
        فقط درباره خدمات این شرکت صحبت کن.
        """

    else:
        base = f"تو دستیار پشتیبانی {business.name} هستی.\nحوزه کاری: {business.field}\nساعت کاری: {business.working_hours}\nتماس: {business.contact}\n{style}\nفقط به فارسی جواب بده."

    return base + _faq_section(faq or [])
