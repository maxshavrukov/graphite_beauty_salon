from django.test import TestCase
from django.urls import reverse

from catalog.tests.factories import (
    make_category,
    make_master,
    make_master_service,
    make_service,
)


class HomePageTests(TestCase):
    def test_home_opens_without_any_data(self) -> None:
        response = self.client.get(reverse("webpages:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("webpages:booking"))

    def test_shows_bookable_service_category_and_master(self) -> None:
        category = make_category(name="Ногтевой сервис")
        service = make_service(category, name="Маникюр классический")
        master = make_master(name="Виолета")
        make_master_service(master, service)

        response = self.client.get(reverse("webpages:home"))

        self.assertContains(response, "Ногтевой сервис")
        self.assertContains(response, "Маникюр классический")
        self.assertContains(response, "Виолета")

    def test_hides_service_without_masters(self) -> None:
        category = make_category(name="Брови")
        make_service(category, name="Ламинирование бровей")

        response = self.client.get(reverse("webpages:home"))

        self.assertNotContains(response, "Ламинирование бровей")
        self.assertNotContains(response, "Брови")

    def test_hides_inactive_service_and_inactive_master(self) -> None:
        category = make_category(name="Массаж")
        service = make_service(category, name="Массаж спины", is_active=False)
        master = make_master(name="Скрытый мастер", is_active=False)
        make_master_service(master, service)

        response = self.client.get(reverse("webpages:home"))

        self.assertNotContains(response, "Массаж спины")
        self.assertNotContains(response, "Скрытый мастер")

    def test_hides_service_if_its_master_service_is_inactive(self) -> None:
        category = make_category(name="Педикюр")
        service = make_service(category, name="Педикюр аппаратный")
        master = make_master(name="Карина")
        make_master_service(master, service, is_active=False)

        response = self.client.get(reverse("webpages:home"))

        self.assertNotContains(response, "Педикюр аппаратный")

    def test_master_without_photo_gets_placeholder(self) -> None:
        master = make_master(name="Карина")
        make_master_service(master)

        response = self.client.get(reverse("webpages:home"))

        self.assertContains(response, "master-photo-empty")


class ServicesPageTests(TestCase):
    def test_empty_page_opens(self) -> None:
        response = self.client.get(reverse("webpages:services"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "скоро появится")

    def test_single_price_is_shown_without_from(self) -> None:
        service = make_service(name="Мужская стрижка")
        make_master_service(make_master(), service, price=500, duration=30)

        response = self.client.get(reverse("webpages:services"))

        self.assertContains(response, "Мужская стрижка")
        self.assertContains(response, "500")
        self.assertContains(response, "30 мин")
        self.assertNotContains(response, "price-from")

    def test_different_prices_show_from_and_duration_range(self) -> None:
        service = make_service(name="Женская стрижка")
        make_master_service(make_master(), service, price=800, duration=60)
        make_master_service(make_master(), service, price=500, duration=45)

        response = self.client.get(reverse("webpages:services"))

        self.assertContains(response, "price-from")
        self.assertContains(response, "500")
        self.assertContains(response, "45–60 мин")

    def test_inactive_master_does_not_affect_price(self) -> None:
        service = make_service(name="Окрашивание")
        make_master_service(make_master(), service, price=1000)
        make_master_service(make_master(is_active=False), service, price=300)

        response = self.client.get(reverse("webpages:services"))

        self.assertContains(response, "1000")
        self.assertNotContains(response, "price-from")

    def test_service_without_masters_is_hidden(self) -> None:
        make_service(name="Ламинирование бровей")

        response = self.client.get(reverse("webpages:services"))

        self.assertNotContains(response, "Ламинирование бровей")


class MasterPageTests(TestCase):
    def test_shows_master_with_own_services_and_prices(self) -> None:
        master = make_master(name="Виолета", slug="violeta", bio="Колорист")
        service = make_service(name="Маникюр классический")
        make_master_service(master, service, price=600, duration=60)

        response = self.client.get(reverse("webpages:master", args=["violeta"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Виолета")
        self.assertContains(response, "Колорист")
        self.assertContains(response, "Маникюр классический")
        self.assertContains(response, "600")
        self.assertContains(response, "60 мин")

    def test_does_not_show_other_masters_price(self) -> None:
        service = make_service(name="Стрижка")
        master = make_master(name="Вадим", slug="vadim")
        other = make_master(name="Карина", slug="karina")
        make_master_service(master, service, price=600)
        make_master_service(other, service, price=900)

        response = self.client.get(reverse("webpages:master", args=["vadim"]))

        self.assertContains(response, "600")
        self.assertNotContains(response, "900")

    def test_inactive_service_is_not_listed(self) -> None:
        master = make_master(slug="karina")
        make_master_service(master, make_service(name="Активная услуга"))
        make_master_service(
            master,
            make_service(name="Выключенная услуга", is_active=False),
        )

        response = self.client.get(reverse("webpages:master", args=["karina"]))

        self.assertContains(response, "Активная услуга")
        self.assertNotContains(response, "Выключенная услуга")

    def test_unknown_master_returns_404(self) -> None:
        response = self.client.get(reverse("webpages:master", args=["nobody"]))

        self.assertEqual(response.status_code, 404)

    def test_inactive_master_returns_404(self) -> None:
        master = make_master(slug="hidden", is_active=False)
        make_master_service(master)

        response = self.client.get(reverse("webpages:master", args=["hidden"]))

        self.assertEqual(response.status_code, 404)

    def test_master_without_services_returns_404(self) -> None:
        make_master(slug="empty")

        response = self.client.get(reverse("webpages:master", args=["empty"]))

        self.assertEqual(response.status_code, 404)

    def test_home_links_to_master_page(self) -> None:
        master = make_master(slug="violeta")
        make_master_service(master)

        response = self.client.get(reverse("webpages:home"))

        self.assertContains(response, reverse("webpages:master", args=["violeta"]))

    def test_master_with_service_in_inactive_category_is_hidden(self) -> None:
        category = make_category(name="Скрытая", is_active=False)
        service = make_service(category, name="Скрытая услуга")
        master = make_master(name="Скрытая Мастер", slug="hidden-cat")
        make_master_service(master, service)

        home = self.client.get(reverse("webpages:home"))
        page = self.client.get(reverse("webpages:master", args=["hidden-cat"]))

        self.assertNotContains(home, "Скрытая Мастер")
        self.assertEqual(page.status_code, 404)


class OtherPagesTests(TestCase):
    def test_booking_page_has_react_container(self) -> None:
        response = self.client.get(reverse("webpages:booking"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="booking-root"')

    def test_admin_and_api_still_reachable(self) -> None:
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.assertEqual(self.client.get("/api/categories/").status_code, 200)
