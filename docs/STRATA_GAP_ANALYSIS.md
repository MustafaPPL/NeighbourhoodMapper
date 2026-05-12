# Gap Analysis: NHS Neighbourhood Hub Tool vs. Strata
**Prepared for:** Internal Review
**Date:** May 2026
**Purpose:** To assess how our in-house neighbourhood hub location tool compares to Strata — the NHS England-endorsed mapping and planning platform — and to identify priority development areas.

---

## Executive Summary

Strata is a well-funded, NHS-endorsed SaaS platform built for broad estate and service planning across England. Our tool has been purpose-built for a different and more specific problem: **identifying and ranking the best locations for neighbourhood hubs across London's ICBs.**

The key finding is that **these tools are not direct competitors — they serve different decisions.** Strata excels at broad strategic planning with rich data integration. Our tool excels at a specific, high-value planning task that Strata cannot currently perform: **automated, transparent, need-weighted hub location ranking.**

However, there are clear gaps in our tool that, if addressed, would significantly strengthen the methodology and the confidence decision-makers can place in the outputs.

---

## What Strata Does That We Don't

These are the most material gaps in our current tool, ranked by strategic importance.

### 1. Travel Time Analysis *(High Priority)*
Strata models how long it takes to reach a service by **walking, cycling, driving, and public transport.** Our tool draws a straight-line radius circle around each candidate — which does not reflect how people actually travel, particularly in areas with poor transport links.

> **So what:** A hub ranked highly by our tool could have poor public transport access. Incorporating travel time would materially improve the real-world validity of our recommendations.

---

### 2. Clinical Need Data (Disease Prevalence) *(High Priority)*
Strata integrates **GP-recorded disease prevalence** (e.g., diabetes, hypertension, COPD) from the NHS Quality and Outcomes Framework (QOF). Our tool uses deprivation as a proxy for need, which is a reasonable but imprecise measure.

> **So what:** Planners targeting specific health conditions (e.g., cardiovascular disease, frailty) cannot currently weight our scores by clinical need. Adding QOF data would directly support condition-specific hub planning.

---

### 3. Estate & Building Intelligence *(Medium Priority)*
Strata draws on NHS estates data (ERIC) to flag **underutilised clinical space and void buildings** near proposed locations. Our tool has no estate intelligence — it could recommend a postcode where no suitable building exists nearby.

> **So what:** Combining our hub scores with estate availability would make outputs immediately more actionable and reduce wasted feasibility time.

---

### 4. Future Demand Modelling *(Medium Priority)*
Strata incorporates **housing development data and ONS population projections** to model where demand will grow over the next 5–10 years. Our tool uses current population figures only.

> **So what:** A hub sited for today's population may not align with where need will be greatest by the time it opens. Forward-looking demand data would strengthen the business case for any recommendation.

---

### 5. Ethnicity Data *(Medium Priority)*
Strata includes **ethnicity breakdown at small-area level** from the 2021 Census. Our tool has no ethnicity dimension.

> **So what:** Given London's diversity and the link between ethnicity and specific health inequalities, this is a notable gap — particularly for ICBs with equity-focused commissioning priorities.

---

### 6. Multi-Scenario Comparison *(Lower Priority)*
Strata allows planners to compare **multiple service configurations side-by-side.** Our tool runs one scenario at a time; users must re-run manually to test alternatives.

> **So what:** This limits the speed at which planners can explore trade-offs. A saved scenarios feature would support faster decision-making.

---

## What We Do That Strata Cannot

These are our **genuine differentiators** — capabilities that Strata does not offer, which justify our tool's continued development alongside, not instead of, Strata.

| Our Capability | Why It Matters |
|---|---|
| **Automated hub candidate suggestion** | Strata requires manual location testing. Our tool automatically surfaces the highest-need candidate postcodes across a geography, with configurable spacing and neighbourhood diversity rules. |
| **User-controlled, transparent need scoring** | Users choose which indices to include and assign explicit weights. Every scoring decision is visible and auditable. Strata's scoring is proprietary — planners cannot see or adjust how need is calculated. |
| **Named neighbourhood alignment** | Our tool operates at the ICB neighbourhood footprint level, aligned to NHS neighbourhood health plans. Strata works at LSOA/PCN level and does not natively support this geography. |
| **Full per-analysis audit trail** | Every run produces a structured audit: geography, indices, weights, catchment, constraints, and timestamp. This supports clinical governance and internal sign-off. |
| **No vendor dependency** | Our tool is fully NHS-owned and open-source. All data, logic, and outputs are under our control. Strata is a third-party SaaS platform with subscription costs and a proprietary methodology. |

---

## At-a-Glance Comparison

| Feature | Our Tool | Strata |
|---|---|---|
| LSOA-level need mapping | Yes | Yes |
| Deprivation (IMD) index | Yes | Yes |
| 65+ population layer | Yes | Partial |
| GP / pharmacy / family hub overlays | Yes | Yes |
| Disease prevalence (QOF) | No | **Yes** |
| Ethnicity data | No | **Yes** |
| Travel time catchments | No | **Yes** |
| Future population projections | No | **Yes** |
| Estate / void space data | No | **Yes** |
| Automated hub candidate suggestion | **Yes** | No |
| User-weighted need scoring | **Yes** | No |
| Named neighbourhood geography | **Yes** | No |
| Per-analysis audit log | **Yes** | No |
| Multi-scenario comparison | No | Yes |
| England-wide coverage | No | Yes |
| NHS-owned / open-source | Yes | No |

---

## Recommended Next Steps

The following are prioritised by **impact on methodology quality and decision-maker confidence**, balanced against development effort.

### Step 1 — Add Travel Time Catchments *(High Impact / Medium Effort)*
Replace straight-line radius circles with public transport and walking isochrones, using open-source routing services (e.g., OpenRouteService) or NHS-approved data (Traveline).

**Outcome:** Recommendations that reflect how patients actually access services — particularly important in areas with poor transport infrastructure.

---

### Step 2 — Integrate QOF Disease Prevalence Data *(High Impact / Low Effort)*
QOF data is publicly available from NHS Digital at no cost. Adding practice-level disease prevalence mapped to LSOA would allow planners to weight need scores by specific health conditions.

**Outcome:** Condition-specific hub planning (e.g., targeting areas of high cardiovascular or frailty burden) with no additional data cost.

---

### Step 3 — Surface Estate Availability Alongside Hub Scores *(Medium Impact / Medium Effort)*
Cross-reference high-scoring locations against ERIC estate data to flag whether NHS-owned or underutilised buildings exist nearby.

**Outcome:** Outputs that connect "where need is greatest" with "where a building could actually go" — reducing the gap between planning tool and feasibility assessment.

---

### Step 4 — Add Ethnicity as a Scoreable Index *(Medium Impact / Low Effort)*
2021 Census ethnicity data is freely available at LSOA level from ONS and could be added as an optional index within the existing scoring framework.

**Outcome:** Supports equity-focused ICBs in targeting communities that may face language, cultural, or access barriers alongside deprivation.

---

### Step 5 — Enable Scenario Saving and Comparison *(Lower Impact / Medium Effort)*
Allow users to save a scoring run and compare it against an alternative configuration within the same session.

**Outcome:** Faster, evidence-based exploration of trade-offs — particularly useful in stakeholder workshops.

---

## Conclusion

Our tool fills a specific gap that Strata does not address: **structured, transparent, automated ranking of neighbourhood hub locations.** This remains a genuine differentiator that warrants continued investment.

The two tools are best understood as **complementary**. A combined workflow — using Strata for broad population and estate context, and our tool for hub candidate generation and ranking — would represent best-in-class planning practice for London ICBs.

The five steps above would close the most significant methodological gaps, strengthen the evidence base underpinning each recommendation, and reduce the need for planners to manually cross-reference both tools.

---

*For questions about this analysis or the underlying tool, please contact the project team.*
