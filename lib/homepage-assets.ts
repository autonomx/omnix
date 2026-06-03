const CATEGORY_BASE = '/homepage/categories';

const categoryImageBySlug: Record<string, string> = {
  'available-today': 'birthday.jpg',
  daily: 'birthday.jpg',
  'cacao-roses': 'rose-bag.jpg',
  'today-vip': 'woshe-royal.jpg',
  'flower-boxes': 'flower-boxes.jpg',
  'standard-boxes': 'standard-flower-box.jpg',
  'vip-boxes': 'vip-flower-box.jpg',
  'rose-envelope': 'rose-bag.jpg',
  'kids-boxes': 'kids-flower-box.jpg',
  bouquets: 'bouquets.jpg',
  'standard-bouquets': 'standard-bouquet.jpg',
  'vip-bouquets': 'vip-bouquet.jpg',
  'woshe-royal': 'woshe-royal.jpg',
  birthday: 'birthday.jpg',
  'birthday-package': 'birthday-packages.jpg',
  'birthday-box': 'birthday-box.jpg',
  'ceremony-design': 'ceremony-design.jpg',
  weddings: 'wedding.jpg',
  condolence: 'condolence.jpg',
  balloons: 'balloons.jpg',
  cakes: 'cakes.jpg'
};

export type HomepageBannerSlide = {
  image: string;
  alt: string;
  eyebrow: string;
  title: string;
  body: string;
};

export const homepageBannerSlides: HomepageBannerSlide[] = [
  {
    image: '/homepage/banners/golara_luxury_floral_hero_banner.jpg',
    alt: 'Luxury Golara floral hero arrangement with warm cream background',
    eyebrow: 'Same-day floral gifting',
    title: 'Flowers that arrive with feeling',
    body: 'Shop ready-today bouquets, premium boxes, and thoughtful occasion gifts with a studio-polished finish.'
  },
  {
    image: '/homepage/banners/banner2.jpeg',
    alt: 'Golara available today banner',
    eyebrow: 'Fresh today',
    title: 'Choose by mood, moment, or color',
    body: 'Romantic pinks, porcelain whites, dramatic berry tones, and refined greens for gifts that feel considered.'
  },
  {
    image: '/homepage/banners/banner3.jpeg',
    alt: 'Golara floral studio banner',
    eyebrow: 'Golara floral studio',
    title: 'Designed around the occasion',
    body: 'Birthday, proposal, wedding, baby, sympathy, and celebration flowers arranged with calm, personal guidance.'
  },
  {
    image: '/homepage/banners/banner4.jpeg',
    alt: 'Golara distance banner',
    eyebrow: 'Distance delivery',
    title: 'Send flowers beautifully from anywhere',
    body: 'Browse clearly, choose confidently, and let the studio coordinate the right floral gift for the delivery moment.'
  }
];

const bestSellerImageBySlug: Record<string, string> = {
  'vip-box-blue': '/homepage/best-seller/dsc09807.jpeg',
  'signiture-round-baby-pink': '/homepage/best-seller/dsc01904_1_1.jpeg',
  'imperium-vip-red-roses': '/homepage/best-seller/4u1a9169.jpeg',
  'imperium-vip-peach': '/homepage/best-seller/dsc09074.jpeg',
  'woshe-grand-cream': '/homepage/best-seller/dsc09367_1.jpeg',
  'woshe-round-hand-bouquet-honey-rose': '/homepage/best-seller/4u1a1444.jpeg',
  'woshe-round-hand-bouquet-ruby-harmony': '/homepage/best-seller/dsc01892.jpeg',
  'woshe-round-hand-bouquet-white-lily': '/homepage/best-seller/11_jpg.jpeg',
  'autumn-design-2': '/homepage/best-seller/01_jpg_3.jpeg',
  'steel-bloom-wild-1001372': '/homepage/best-seller/steel_bloom.jpeg',
  'woshe-christmas-collection-round-hand-bouquet': '/homepage/best-seller/4u1a0378.jpeg',
  'vip-box-red-pink': '/homepage/best-seller/4u1a5074.jpeg',
  'imperium-pink': '/homepage/best-seller/imperium_pink.jpeg',
  'teddy-bouquet': '/homepage/best-seller/4u1a4869.jpeg',
  'steel-bloom-wild-1001110': '/homepage/best-seller/dsc01555.jpeg',
  'dark-blue-design': '/homepage/best-seller/img_8181.jpeg',
  'pastel-green-design': '/homepage/best-seller/4u1a3379.jpeg',
  'yellow-pink-design': '/homepage/best-seller/982ebb5a-06d7-4674-b990-5533d828cf23.jpeg',
  'woshe-round-hand-bouquet-red': '/homepage/best-seller/dsc01902.jpeg',
  'woshe-round-hand-bouquet-pink': '/homepage/best-seller/img_3595.jpeg',
  'cream-pink-design': '/homepage/best-seller/4u1a8936.jpeg',
  'light-green-design': '/homepage/best-seller/dsc00044.jpeg',
  'pink-roses-pink-belle': '/homepage/best-seller/01_jpg_3.jpeg',
  'maroon-belle': '/homepage/best-seller/steel_bloom.jpeg'
};

export function homepageBestSellerImage(slug: string) {
  return bestSellerImageBySlug[slug] ?? `/homepage/best-seller/${slug}.jpeg`;
}

export function homepageCategoryImage(slug: string) {
  const filename = categoryImageBySlug[slug] ?? `${slug}.jpg`;
  return `${CATEGORY_BASE}/${filename}`;
}
