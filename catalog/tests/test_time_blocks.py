from datetime import date, time
from django.test import TestCase
from catalog.models import Master, TimeBlock
from catalog.services import filter_candidates_by_time_blocks


class FilterCandidatesByTimeBlocksTests(TestCase):

    def test_removes_candidate_that_overlaps_time_block(self):
        master = Master.objects.create(
            name="Мастер с блокировкой",
            slug="master-with-block",
        )

        block = TimeBlock.objects.create(
            master=master,
            date=date(2026, 9, 7),
            start_time=time(10, 15),
            end_time=time(11, 0),
            reason="Личные дела",
        )

        result = filter_candidates_by_time_blocks(
            candidates=[time(10, 0)],
            duration_minutes=30,
            time_blocks=[block],
        )

        self.assertEqual(result, [])

    def test_keeps_candidate_that_does_not_overlap_time_block(self):
        master = Master.objects.create(
            name="Мастер с блокировкой",
            slug="master-with-block-2",
        )

        block = TimeBlock.objects.create(
            master=master,
            date=date(2026, 9, 7),
            start_time=time(11, 0),
            end_time=time(12, 0),
            reason="Личные дела",
        )

        result = filter_candidates_by_time_blocks(
            candidates=[time(10, 0)],
            duration_minutes=30,
            time_blocks=[block],
        )

        self.assertEqual(
            result,
            [time(10, 0)],
        )

    def test_keeps_candidate_when_it_only_touches_time_block_boundary(self):
        master = Master.objects.create(
            name="Мастер с блокировкой",
            slug="master-with-block-3",
        )

        block = TimeBlock.objects.create(
            master=master,
            date=date(2026, 9, 7),
            start_time=time(10, 30),
            end_time=time(11, 0),
            reason="Личные дела",
        )

        result = filter_candidates_by_time_blocks(
            candidates=[time(10, 0)],
            duration_minutes=30,
            time_blocks=[block],
        )

        self.assertEqual(
            result,
            [time(10, 0)],
        )

    def test_filters_blocked_candidate_but_keeps_available_one(self):
        master = Master.objects.create(
            name="Мастер с блокировкой",
            slug="master-with-block-4",
        )

        block = TimeBlock.objects.create(
            master=master,
            date=date(2026, 9, 7),
            start_time=time(10, 15),
            end_time=time(11, 0),
            reason="Личные дела",
        )

        result = filter_candidates_by_time_blocks(
            candidates=[
                time(10, 0),
                time(11, 0),
            ],
            duration_minutes=30,
            time_blocks=[block],
        )

        self.assertEqual(
            result,
            [time(11, 0)],
        )