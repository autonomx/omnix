import Image from 'next/image';
import Link from 'next/link';
import { MessageCircle, Sparkles, Truck } from 'lucide-react';
import type { HomepageBannerSlide } from '@/lib/homepage-assets';

interface HomepageBannerSlideshowProps {
  slides: HomepageBannerSlide[];
}

export function HomepageBannerSlideshow({ slides }: HomepageBannerSlideshowProps) {
  const heroSlide = slides[0];

  if (!heroSlide) {
    return null;
  }

  return (
    <section
      id="home-hero"
      data-section="home-hero"
      aria-labelledby="home-hero-heading"
      className="relative overflow-hidden bg-[#fff7f1] px-4 py-5 md:px-8 md:py-8"
    >
      <div className="relative mx-auto min-h-[600px] max-w-[1520px] overflow-hidden rounded-[2rem] border border-rosewood/10 bg-stone-900 shadow-[0_26px_70px_rgba(111,36,56,0.14)] md:min-h-[680px]">
        <Image
          src={heroSlide.image}
          alt={heroSlide.alt}
          fill
          priority
          className="object-cover"
          sizes="100vw"
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,248,241,0.96)_0%,rgba(255,248,241,0.88)_34%,rgba(255,248,241,0.42)_58%,rgba(43,29,32,0.12)_100%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_14%_28%,rgba(255,255,255,0.9)_0%,rgba(255,255,255,0.18)_34%,rgba(255,255,255,0)_62%)]" />

        <div className="relative z-10 flex min-h-[600px] items-center px-6 py-12 md:min-h-[680px] md:px-12 lg:px-16">
          <div className="max-w-2xl text-stone-800">
            <p className="inline-flex rounded-full border border-rosewood/10 bg-white/72 px-5 py-2 text-xs font-semibold uppercase tracking-[0.32em] text-olive shadow-sm">
              {heroSlide.eyebrow}
            </p>
            <h1 id="home-hero-heading" className="mt-8 max-w-2xl font-display text-5xl leading-[0.95] text-rosewood md:text-7xl lg:text-8xl">
              {heroSlide.title}
            </h1>
            <p className="mt-6 max-w-xl text-base leading-8 text-stone-700 md:text-lg md:leading-9">
              {heroSlide.body}
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link href="/categories/available-today" className="inline-flex rounded-full bg-rosewood px-7 py-3.5 text-sm font-semibold text-white shadow-[0_14px_30px_rgba(111,36,56,0.18)] transition hover:-translate-y-0.5 hover:bg-stone-900 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-olive/30">
                Shop available today
              </Link>
              <Link href="/products" className="inline-flex rounded-full border border-rosewood/20 bg-white/78 px-7 py-3.5 text-sm font-semibold text-rosewood shadow-sm transition hover:-translate-y-0.5 hover:border-rosewood focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-olive/30">
                All products
              </Link>
              <Link href="/#best-sellers" className="inline-flex rounded-full border border-rosewood/15 bg-white/58 px-7 py-3.5 text-sm font-semibold text-rosewood shadow-sm transition hover:-translate-y-0.5 hover:border-rosewood focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-olive/30">
                Best sellers
              </Link>
            </div>

            <div className="mt-10 flex flex-wrap gap-3 text-sm font-semibold text-stone-700">
              <div className="inline-flex items-center gap-2 rounded-full border border-rosewood/10 bg-white/72 px-4 py-2 shadow-sm">
                <Truck aria-hidden="true" className="h-4 w-4 text-rosewood" />
                Same-day options
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-rosewood/10 bg-white/72 px-4 py-2 shadow-sm">
                <Sparkles aria-hidden="true" className="h-4 w-4 text-rosewood" />
                Premium finish
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-rosewood/10 bg-white/72 px-4 py-2 shadow-sm">
                <MessageCircle aria-hidden="true" className="h-4 w-4 text-rosewood" />
                Sales guidance
              </div>
            </div>
          </div>
        </div>

        <div className="absolute bottom-6 right-6 hidden rounded-full border border-white/35 bg-white/72 px-5 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-rosewood shadow-sm md:block">
          Golara studio selection
        </div>
      </div>
    </section>
  );
}
