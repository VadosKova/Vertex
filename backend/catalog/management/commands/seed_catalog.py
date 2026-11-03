from django.core.management.base import BaseCommand

from catalog.models import Brand, Category, Product, ProductSize

CATEGORIES = [("tshirts", "Футболки", "T-shirts"), ("hoodies", "Худі", "Hoodies"),
              ("jeans", "Джинси", "Jeans"), ("dresses", "Сукні", "Dresses")]

# розмір: груди, талія, стегна (заміри тіла, см, (мін, макс))
TOPS = {"S": ((88, 92), (74, 78), (92, 96)), "M": ((92, 100), (78, 86), (96, 102)),
        "L": ((100, 108), (86, 94), (102, 110)), "XL": ((108, 116), (94, 102), (110, 118))}
DRESSES = {"XS": ((80, 84), (62, 66), (86, 90)), "S": ((84, 88), (66, 70), (90, 94)),
           "M": ((88, 94), (70, 76), (94, 100)), "L": ((94, 100), (76, 82), (100, 106))}
JEANS = {"28": ((80, 85), (70, 74), (88, 92)), "30": ((85, 90), (74, 79), (92, 97)),
         "32": ((90, 96), (79, 85), (97, 102)), "34": ((96, 102), (85, 91), (102, 108))}

DEMO = [("Vertex Basics", "Basic Tee", "tshirts", TOPS, 0.05),
        ("Vertex Basics", "Classic Hoodie", "hoodies", TOPS, 0.04),
        ("Vertex Denim", "Straight Jeans", "jeans", JEANS, 0.02),
        ("Vertex Studio", "Wrap Dress", "dresses", DRESSES, 0.05)]


class Command(BaseCommand):
    help = "Seed categories and a few template products (dev/demo)."

    def handle(self, *args, **opts):
        categories = {}
        for slug, uk, en in CATEGORIES:
            categories[slug], _ = Category.objects.get_or_create(slug=slug, defaults={"name_uk": uk, "name_en": en})

        for brand_name, title, slug, chart, stretch in DEMO:
            brand, _ = Brand.objects.get_or_create(name=brand_name)
            product, created = Product.objects.get_or_create(
                brand=brand, title=title,
                defaults={"category": categories[slug], "is_template": True, "fabric_stretch": stretch,
                          "gender": "female" if slug == "dresses" else "unisex"})
            if created:
                for i, (label, (c, w, h)) in enumerate(chart.items()):
                    ProductSize.objects.create(product=product, label=label, order=i,
                                               chest_min=c[0], chest_max=c[1], waist_min=w[0], waist_max=w[1],
                                               hips_min=h[0], hips_max=h[1])
        self.stdout.write(self.style.SUCCESS("Catalog seeded."))