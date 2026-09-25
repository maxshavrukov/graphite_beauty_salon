from datetime import date, time

from django.test import TestCase

from catalog.models import TimeBlock
from catalog.services import filter_candidates_by_time_blocks
from catalog.tests.factories import make_master


class FilterCandidatesByTimeBlocksTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.date = date(2026, 9, 7)

    def test_removes_candidate_that_overlaps_time_block(self):
        block = TimeBlock.objects.create(
            master=self.master,
            date=self.date,
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
        block = TimeBlock.objects.create(
            master=self.master,
            date=self.date,
            start_time=time(11, 0),
            end_time=time(12, 0),
            reason="Личные дела",
        )

        result = filter_candidates_by_time_blocks(
            candidates=[time(10, 0)],
            duration_minutes=30,
            time_blocks=[block],
        )

        self.assertEqual(result, [time(10, 0)])

    def test_keeps_candidate_when_it_only_touches_time_block_boundary(self):
        block = TimeBlock.objects.create(
            master=self.master,
            date=self.date,
            start_time=time(10, 30),
            end_time=time(11, 0),
            reason="Личные дела",
        )

        result = filter_candidates_by_time_blocks(
            candidates=[time(10, 0)],
            duration_minutes=30,
            time_blocks=[block],
        )

        self.assertEqual(result, [time(10, 0)])

    def test_filters_blocked_candidate_but_keeps_available_one(self):
        block = TimeBlock.objects.create(
            master=self.master,
            date=self.date,
            start_time=time(10, 15),
            end_time=time(11, 0),
            reason="Личные дела",
        )

        result = filter_candidates_by_time_blocks(
            candidates=[time(10, 0), time(11, 0)],
            duration_minutes=30,
            time_blocks=[block],
        )

        self.assertEqual(result, [time(11, 0)])
