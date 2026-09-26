import "./style.css";
import { fmtRho, loadStats } from "./common";

loadStats()
  .then((s) => {
    document.getElementById("stats-list")!.innerHTML = `
      <li>HVI rank vs frequent mental distress: ${fmtRho(s.hvi_rank_vs_mhlth)}</li>
      <li>HVI rank vs frequent mental distress, controlling for median income: ${fmtRho(s.hvi_rank_vs_mhlth_partial_income)}</li>
      <li>HVI rank vs frequent mental distress, controlling for median income and percent Black population: ${fmtRho(s.hvi_rank_vs_mhlth_partial_income_pct_black)}</li>
      <li>Street trees per km² (2015) vs frequent mental distress: ${fmtRho(s.trees_per_km2_vs_mhlth)}</li>
      <li>Street trees per km² (2015) vs frequent mental distress, controlling for median income: ${fmtRho(s.trees_per_km2_vs_mhlth_partial_income)}</li>`;
  })
  .catch(() => {
    document.getElementById("stats-list")!.innerHTML = "<li>stats.json could not be loaded.</li>";
  });
