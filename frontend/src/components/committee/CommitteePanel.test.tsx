import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CommitteePanel } from "./CommitteePanel";
import type { CommitteeConsensus } from "@/lib/api/stocks-types";

/** AI Multi-Agent Investment Committee -- every field here is
 * verbatim backend output already computed by the Consensus Engine
 * (see src.ai_evolution.committee.consensus); these tests lock down
 * that agent opinions, agreement/disagreement, most optimistic/
 * conservative, the consensus explanation, and rejected alternatives
 * are all rendered from real data, and that a null committee renders
 * nothing rather than a fabricated placeholder. */

function buildCommittee(overrides: Partial<CommitteeConsensus> = {}): CommitteeConsensus {
  return {
    final_decision: "BUY",
    final_confidence: 72.5,
    participant_count: 8,
    directional_count: 5,
    agreement_pct: 80,
    disagreement_pct: 20,
    disagreement_score: 12.3,
    most_optimistic_agent: "Technical Analysis Agent",
    most_optimistic_stance: "BULLISH",
    most_conservative_agent: "Risk Management Agent",
    most_conservative_stance: "BEARISH",
    consensus_reasoning_ar: "توصلت لجنة الاستثمار إلى توافق بنسبة 80% حول قرار (شراء).",
    rejected_alternatives: [
      {
        agent_name: "Risk Management Agent",
        role: "risk",
        stance: "BEARISH",
        confidence: 40,
        reasoning: "مخاطر مرتفعة بسبب تقلب عالٍ.",
        rejection_reason: "تم ترجيح الرأي الأغلب لأن وزنه المرجح الإجمالي يفوق الوزن المرجح لهذا الرأي (0.52).",
      },
    ],
    weighted_votes: { "Technical Analysis Agent": 0.96, "Risk Management Agent": -0.52 },
    opinions: [
      {
        agent_name: "Technical Analysis Agent",
        role: "technical",
        stance: "BULLISH",
        confidence: 80,
        reasoning: "التحليل الفني ساهم بـ +15.0 نقطة.",
        evidence: ["التحليل الفني: +15.0 نقطة (وزن 0.25، ثقة 80%)"],
        rejection_reasons: [],
        used_llm: false,
      },
      {
        agent_name: "Macro Economy Agent",
        role: "macro",
        stance: "UNAVAILABLE",
        confidence: 0,
        reasoning: "لا يوجد مصدر بيانات كلية حقيقي.",
        evidence: [],
        rejection_reasons: ["لا يوجد مصدر بيانات كلية حقيقي في هذا النظام حالياً."],
        used_llm: false,
      },
    ],
    ...overrides,
  };
}

describe("CommitteePanel", () => {
  it("renders nothing when the committee did not run", () => {
    const { container } = render(<CommitteePanel committee={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the final decision and confidence", () => {
    render(<CommitteePanel committee={buildCommittee()} />);
    expect(screen.getByText(/شراء \(73%\)/)).toBeInTheDocument();
  });

  it("renders agreement, disagreement, and disagreement score", () => {
    render(<CommitteePanel committee={buildCommittee()} />);
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.getByText("12.3")).toBeInTheDocument();
  });

  it("renders the most optimistic and most conservative agent", () => {
    render(<CommitteePanel committee={buildCommittee()} />);
    expect(screen.getByText("Technical Analysis Agent", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText("Risk Management Agent", { selector: "p" })).toBeInTheDocument();
  });

  it("renders the consensus reasoning explanation", () => {
    render(<CommitteePanel committee={buildCommittee()} />);
    expect(screen.getByText(/توصلت لجنة الاستثمار إلى توافق/)).toBeInTheDocument();
  });

  it("renders one card per agent opinion, including evidence", () => {
    render(<CommitteePanel committee={buildCommittee()} />);
    expect(screen.getByText(/التحليل الفني: \+15\.0 نقطة/)).toBeInTheDocument();
    expect(screen.getByText("متفائل")).toBeInTheDocument();
    expect(screen.getByText("غير متوفر")).toBeInTheDocument();
  });

  it("renders why alternative opinions were rejected", () => {
    render(<CommitteePanel committee={buildCommittee()} />);
    expect(screen.getByText("لماذا رُفضت الآراء البديلة؟")).toBeInTheDocument();
    expect(screen.getByText(/تم ترجيح الرأي الأغلب/)).toBeInTheDocument();
  });

  it("omits the rejected-alternatives section when there are none", () => {
    render(<CommitteePanel committee={buildCommittee({ rejected_alternatives: [] })} />);
    expect(screen.queryByText("لماذا رُفضت الآراء البديلة؟")).not.toBeInTheDocument();
  });
});
