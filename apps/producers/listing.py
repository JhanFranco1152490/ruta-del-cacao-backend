from django.db.models import Q

from .models import Producer


def list_producers(filters):
    queryset = Producer.objects.all()

    search = filters.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(identity_document__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(member_code__icontains=search)
        )

    if status := filters.get("status"):
        queryset = queryset.filter(status=status)

    if municipality_code := filters.get("municipality_code"):
        queryset = queryset.filter(municipality_code=municipality_code)

    page = filters.get("page", 1)
    page_size = filters.get("page_size", 20)
    start = (page - 1) * page_size
    total = queryset.count()
    results = list(queryset.order_by("last_name", "first_name", "id")[start : start + page_size])

    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "results": results,
    }
