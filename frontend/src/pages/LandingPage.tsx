import { useSelector } from "react-redux";
import { selectAuth } from "../store/authSlice";
import { LandingNavbar } from "../components/landing/LandingNavbar";
import { HeroSection } from "../components/landing/HeroSection";
import { FeaturesStrip } from "../components/landing/FeaturesStrip";
import { HowItWorksSection } from "../components/landing/HowItWorksSection";
import { DemoSection } from "../components/landing/DemoSection";
import { StatsSection } from "../components/landing/StatsSection";
import { CTASection } from "../components/landing/CTASection";

export function LandingPage() {
  const { user } = useSelector(selectAuth);
  const isAuthed = !!user;

  return (
    <div className="landing-page">
      <LandingNavbar isAuthed={isAuthed} user={user} />
      <main>
        <HeroSection isAuthed={isAuthed} />
        <FeaturesStrip />
        <HowItWorksSection />
        <DemoSection />
        <StatsSection />
        <CTASection isAuthed={isAuthed} />
      </main>
    </div>
  );
}
