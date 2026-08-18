from polyadmin.core.pagination import paginate


def test_paginate_first_page():
    page = paginate(list(range(30)), page=1, page_size=10)
    assert page.items == list(range(10))
    assert page.number == 1
    assert page.num_pages == 3
    assert page.has_previous is False
    assert page.has_next is True
    assert page.previous_page is None
    assert page.next_page == 2


def test_paginate_last_page():
    page = paginate(list(range(25)), page=3, page_size=10)
    assert page.items == list(range(20, 25))
    assert page.has_previous is True
    assert page.has_next is False
    assert page.next_page is None


def test_paginate_empty():
    page = paginate([], page=1, page_size=10)
    assert page.items == []
    assert page.num_pages == 1
    assert page.has_previous is False
    assert page.has_next is False


def test_paginate_clamps_invalid_inputs():
    page = paginate(list(range(5)), page=0, page_size=0)
    assert page.number == 1
    assert page.page_size == 1
