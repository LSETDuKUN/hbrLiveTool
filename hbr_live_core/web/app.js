/* HBR Live Web Workbench Frontend (Roadmap F2 / F3 / F5, Option C) */
(function () {
  "use strict";

  const MULTIPLIER_GROUPS = [
    {
      title: "基础伤害",
      color: "var(--dim)",
      fields: [["base", "基础伤害（可空）"]],
    },
    {
      title: "连击乘区",
      color: "var(--cyan)",
      fields: [
        ["chain_expression", "颗数 × 每颗倍率"],
        ["chain", "连击合计 %"],
      ],
    },
    {
      title: "加攻乘区",
      color: "var(--pink)",
      fields: [
        ["attack", "普通加攻 %"],
        ["element_attack", "元素加攻 %"],
        ["mind_eye", "心眼 %"],
        ["servant_mind_eye", "仆人心眼（另加）%"],
        ["field", "场地 %"],
        ["charge", "充能 %"],
      ],
    },
    {
      title: "技能独立修正",
      color: "var(--mint)",
      fields: [
        ["token_bonus", "Token 增伤 %"],
        ["dp_bonus", "对 DP 特攻 %"],
        ["hp_bonus", "对 HP 特攻 %"],
        ["health_factor", "技能资源比例倍率"],
        ["down_factor", "倒地条件倍率"],
        ["other_factor", "其他独立倍率"],
      ],
    },
    {
      title: "暴击乘区",
      color: "var(--gold)",
      fields: [
        ["critical_bonus", "普通爆伤（含基础50）%"],
        ["element_critical_bonus", "元素爆伤 %"],
      ],
    },
    {
      title: "减防乘区",
      color: "var(--rose)",
      fields: [
        ["defense_down", "普通减防 %"],
        ["element_defense_down", "元素减防 %"],
        ["fragile", "脆弱 %"],
      ],
    },
    {
      title: "弱点与抗性",
      color: "var(--lavender)",
      fields: [
        ["weapon_bonus", "武器弱点加成 %"],
        ["element_bonus", "元素弱点加成 %"],
        ["weakness_deepen", "弱点加深 %"],
        ["resistance", "抗性 %"],
      ],
    },
    {
      title: "破坏率与 OD",
      color: "var(--cyan)",
      fields: [
        ["destruction", "当前破坏率 %"],
        ["od", "OD 倍率"],
      ],
    },
  ];

  const SKILL_PARAM_DEFS = [
    ["min_power", "最小威力"],
    ["max_power", "最大威力"],
    ["difference", "属性差阈值"],
    ["level", "技能等级"],
    ["enemy", "敌方防御参考值"],
    ["orb", "宝珠等级 (1-5)"],
    ["growth_min", "最小威力等级成长"],
    ["growth_max", "最大威力等级成长"],
    ["power", "力量"],
    ["dexterity", "灵巧"],
    ["toughness", "体力"],
    ["spirit", "精神"],
    ["wisdom", "智慧"],
    ["luck", "幸运"],
    ["weight_power", "力量权重"],
    ["weight_dexterity", "灵巧权重"],
    ["weight_toughness", "体力权重"],
    ["weight_spirit", "精神权重"],
    ["weight_wisdom", "智慧权重"],
    ["weight_luck", "幸运权重"],
    ["calamity", "灾厄属性下降"],
    ["fear_of_devil", "大灾厄属性下降"],
    ["critical_rate_bonus", "普通暴击率加成 %"],
    ["element_critical_rate_bonus", "元素暴击率加成 %"],
    ["morale_level", "士气等级"],
    ["od_gain_bonus", "OD 饰品获取增幅 %"],
    ["sp_consumed", "预计消耗 SP"],
    ["sp_cap", "效果封顶 SP"],
    ["own_dp", "自身当前 DP"],
    ["own_dp_max", "自身 DP 上限"],
    ["dp_zero_factor", "0 DP 时倍率"],
    ["dp_full_factor", "满 DP 时倍率"],
  ];

  const STAT_LABELS = [
    ["power", "力量"],
    ["dexterity", "灵巧"],
    ["toughness", "体力"],
    ["spirit", "精神"],
    ["wisdom", "智慧"],
    ["luck", "幸运"],
  ];

  const DEFAULTS = {
    base: "",
    chain_expression: "0 × 25%",
    chain: "0",
    attack: "0",
    element_attack: "0",
    mind_eye: "0",
    servant_mind_eye: "0",
    field: "0",
    charge: "0",
    token_bonus: "0",
    dp_bonus: "0",
    hp_bonus: "0",
    health_factor: "1.0",
    down_factor: "1.0",
    other_factor: "1.0",
    critical_bonus: "50.0",
    element_critical_bonus: "0",
    defense_down: "0",
    element_defense_down: "0",
    fragile: "0",
    weapon_bonus: "0",
    element_bonus: "0",
    weakness_deepen: "0",
    resistance: "0",
    destruction: "100.0",
    od: "1.0",
  };

  const state = {
    mode: "live",
    snapshot: { connected: false, players: [], enemies: [] },
    autofilledValues: { ...DEFAULTS },
    currentValues: { ...DEFAULTS },
    params: { orb: "5" },
    flags: { critical: true, penetration_critical: false, absorbed: false },
    pool: "hp",
    damageMetric: "raw",
    useSkill: false,
    damageOrbEnabled: false,
    useDestruction: false,
    useDpScaling: false,
    spScaling: false,
    spDrScaling: false,
    hitWeights: "",
    chainDirty: false,
    filledChain: 0,
    hpAdjustments: {},
    shieldState: null,
    autoPoolBlocked: false,
    enemyStatOverride: null,
    proposals: [],
    plotData: null,
    plotDamage: 1,
    teams: [],
    drafts: [],
    selectedArchiveRecord: null,
    offlineTeamRecord: null,
    offlineSkillChoices: {},
    offlineStatuses: [],
  };

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(path, opts);
    const data = await resp.json();
    if (!resp.ok && data && data.error) {
      throw new Error(data.error);
    }
    return data;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function fmtNum(val, digits = 2) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) return "—";
    return Number(val).toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  // ---- Build Multiplier Cards & Skill Parameter Inputs ----
  function buildMultiplierDOM() {
    const container = $("multiplier-groups-container");
    container.innerHTML = "";
    MULTIPLIER_GROUPS.forEach((group) => {
      const card = document.createElement("div");
      card.className = "mgroup-card";
      card.style.setProperty("--group-accent", group.color);

      const head = document.createElement("div");
      head.className = "mgroup-head";
      head.innerHTML = `<span class="mgroup-title">${group.title}</span><span class="hint">${group.fields.length} 项</span>`;
      card.appendChild(head);

      const body = document.createElement("div");
      group.fields.forEach(([key, label]) => {
        const row = document.createElement("div");
        row.className = "mfield-row";
        row.dataset.mrowKey = key;
        row.id = `mrow-${key}`;
        row.innerHTML = `
          <span class="mfield-label">${label}</span>
          <div class="mfield-controls">
            <button type="button" class="mfield-reset hidden" data-reset-key="${key}" title="恢复自动填充值">↺</button>
            <input type="text" class="input-text mfield-input" id="mval-${key}" data-mkey="${key}" value="${state.currentValues[key] ?? ""}" />
          </div>
        `;
        body.appendChild(row);
      });
      head.addEventListener("click", () => body.classList.toggle("hidden"));
      card.appendChild(body);
      container.appendChild(card);
    });

    container.querySelectorAll(".mfield-input").forEach((inp) => {
      inp.addEventListener("input", () => {
        const key = inp.dataset.mkey;
        state.currentValues[key] = inp.value;
        if (key === "chain_expression") {
          state.chainDirty = true;
        }
        updateModifiedHighlights();
      });
      inp.addEventListener("change", () => runCompute());
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") runCompute();
      });
    });

    container.querySelectorAll(".mfield-reset").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.resetKey;
        state.currentValues[key] = state.autofilledValues[key] ?? "";
        const inp = $(`mval-${key}`);
        if (inp) inp.value = state.currentValues[key];
        if (key === "chain_expression") state.chainDirty = true;
        updateModifiedHighlights();
        runCompute();
      });
    });

    const pGrid = $("skill-params-grid");
    pGrid.innerHTML = "";
    SKILL_PARAM_DEFS.forEach(([key, label]) => {
      const cell = document.createElement("div");
      cell.className = "field";
      cell.innerHTML = `<label>${label}</label><input type="text" class="input-text" data-param="${key}" value="${state.params[key] ?? ""}" />`;
      pGrid.appendChild(cell);
    });

    document.querySelectorAll("[data-param]").forEach((inp) => {
      inp.addEventListener("input", () => {
        state.params[inp.dataset.param] = inp.value;
      });
      inp.addEventListener("change", () => runCompute());
    });
  }

  function isFieldModified(key) {
    const a = String(state.autofilledValues[key] ?? "").trim();
    const b = String(state.currentValues[key] ?? "").trim();
    if (a === b) return false;
    const na = Number(a);
    const nb = Number(b);
    if (a !== "" && b !== "" && !Number.isNaN(na) && !Number.isNaN(nb)) {
      return Math.abs(na - nb) > 1e-7;
    }
    return true;
  }

  function updateModifiedHighlights() {
    let count = 0;
    Object.keys(DEFAULTS).forEach((key) => {
      const row = $(`mrow-${key}`);
      if (!row) return;
      const mod = isFieldModified(key);
      if (mod) count++;
      row.classList.toggle("modified", mod);
      const btn = row.querySelector(".mfield-reset");
      if (btn) btn.classList.toggle("hidden", !mod);
    });
    const badge = $("modified-count-badge");
    const resetAll = $("btn-reset-all-overrides");
    badge.textContent = `${count} 项已手改`;
    badge.classList.toggle("hidden", count === 0);
    resetAll.classList.toggle("hidden", count === 0);
  }

  function syncInputsFromState() {
    Object.keys(DEFAULTS).forEach((key) => {
      const inp = $(`mval-${key}`);
      if (inp) inp.value = state.currentValues[key] ?? "";
    });
    document.querySelectorAll("[data-param]").forEach((inp) => {
      const k = inp.dataset.param;
      inp.value = state.params[k] ?? "";
    });
    $("flag-critical").checked = !!state.flags.critical;
    $("flag-penetration_critical").checked = !!state.flags.penetration_critical;
    $("flag-absorbed").checked = !!state.flags.absorbed;
    $("toggle-use-skill").checked = !!state.useSkill;
    $("toggle-damage-orb").checked = !!state.damageOrbEnabled;
    $("toggle-use-destruction").checked = !!state.useDestruction;
    $("toggle-dp-scaling").checked = !!state.useDpScaling;
    $("toggle-sp-dr-scaling").checked = !!state.spDrScaling;
    $("input-hit-weights").value = state.hitWeights || "";

    document.querySelectorAll("#pool-seg .seg-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.pool === state.pool);
    });
    document.querySelectorAll("#metric-seg .seg-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.metric === state.damageMetric);
    });
    updateModifiedHighlights();
  }

  // ---- Snapshot & Prepare Workflow ----
  async function loadSnapshot(autoFill = true) {
    const snap = await api("GET", "/snapshot");
    state.snapshot = snap;
    const badge = $("connection-badge");
    if (snap.offline) {
      badge.textContent = "离线配队试算";
      badge.className = "status-pill offline";
    } else if (snap.connected) {
      badge.textContent = `已连接实战 · ${snap.run_id || ""}`;
      badge.className = "status-pill live";
    } else {
      badge.textContent = "未连接实战（可手填或切换离线）";
      badge.className = "status-pill";
    }

    const pBox = $("live-player-select");
    const eBox = $("live-enemy-select");
    const oldP = pBox.value;
    const oldE = eBox.value;
    pBox.innerHTML = "";
    (snap.players || []).forEach((p, idx) => {
      const opt = document.createElement("option");
      opt.value = String(p.actor_id);
      opt.textContent = `${idx + 1}. ${p.name || p.actor || p.style_label || "未命名"}`;
      pBox.appendChild(opt);
    });
    if (oldP && [...pBox.options].some((o) => o.value === oldP)) {
      pBox.value = oldP;
    }

    eBox.innerHTML = "";
    (snap.enemies || []).forEach((e, idx) => {
      const opt = document.createElement("option");
      opt.value = String(e.address);
      opt.textContent = `${idx + 1}. ${e.name || "敌人"} (DP ${e.dp ?? 0} / HP ${e.hp ?? 0})`;
      eBox.appendChild(opt);
    });
    if (oldE && [...eBox.options].some((o) => o.value === oldE)) {
      eBox.value = oldE;
    }

    if (autoFill && snap.connected && (snap.players || []).length && (snap.enemies || []).length) {
      await runPrepare();
    } else {
      await runCompute();
    }
  }

  function selectedActorAndEnemy() {
    const players = state.snapshot.players || [];
    const enemies = state.snapshot.enemies || [];
    const pVal = $("live-player-select").value;
    const eVal = $("live-enemy-select").value;
    const p = players.find((x) => String(x.actor_id) === pVal) || players[0];
    const e = enemies.find((x) => String(x.address) === eVal) || enemies[0];
    return {
      actor_id: p ? p.actor_id : null,
      enemy_address: e ? e.address : null,
    };
  }

  function currentOptions() {
    return {
      transcend: $("mode-transcend").value,
      transcend_element: $("mode-transcend-el").value,
      high_boost: $("mode-high-boost").value,
      form_choice: $("skill-form-select").value,
      enemy_stat: state.enemyStatOverride,
      damage_metric: state.damageMetric,
    };
  }

  async function runPrepare() {
    const { actor_id, enemy_address } = selectedActorAndEnemy();
    if (actor_id === null || enemy_address === null) return;
    const prep = await api("POST", "/damage/prepare", {
      actor_id,
      enemy_address,
      options: currentOptions(),
    });
    applyPreparedToState(prep);
    await runCompute();
  }

  function applyPreparedToState(prep) {
    if (prep.form_info) {
      const fBox = $("skill-form-select");
      fBox.innerHTML = "";
      (prep.form_info.labels || ["无切换形态"]).forEach((lbl) => {
        const opt = document.createElement("option");
        opt.value = lbl;
        opt.textContent = lbl;
        fBox.appendChild(opt);
      });
      fBox.value = prep.form_info.selected_label || fBox.options[0].value;
    }

    if (!prep.ok) {
      if (prep.fill_notes) $("fill-notes-box").textContent = prep.fill_notes;
      if (prep.sequence_error) $("seq-message").textContent = prep.sequence_error;
      return;
    }

    if (state.enemyStatOverride === null) {
      $("shared-enemy-stat").value = prep.live_enemy_stat ?? "";
      $("enemy-stat-badge").textContent = "敌方属性 · 读取";
      $("enemy-stat-badge").className = "badge";
    } else {
      $("enemy-stat-badge").textContent = "敌方属性 · 手动";
      $("enemy-stat-badge").className = "badge badge-gold";
    }

    const vals = { ...DEFAULTS, ...(prep.values || {}) };
    vals.chain_expression = prep.chain_expression || "0 × 25%";
    state.autofilledValues = { ...vals };
    state.currentValues = { ...vals };
    state.params = { ...(prep.params || {}) };
    state.flags = { ...(prep.flags || state.flags) };
    state.pool = prep.pool || "auto";
    state.useSkill = !!prep.use_skill;
    state.damageOrbEnabled = !!prep.damage_orb_enabled;
    state.useDestruction = !!prep.use_destruction;
    state.useDpScaling = !!prep.use_dp_scaling;
    state.spScaling = !!prep.sp_scaling;
    state.spDrScaling = !!prep.sp_dr_scaling;
    state.hitWeights = prep.hit_weights_str || "";
    state.chainDirty = false;
    state.filledChain = prep.filled_chain;
    state.hpAdjustments = prep.hp_adjustments || {};
    state.shieldState = prep.shield_state || null;
    state.autoPoolBlocked = !!prep.auto_pool_blocked;

    $("current-skill-title").textContent = prep.skill_title || "已自动填充";
    $("hit-source-note").textContent = prep.hit_note || "";
    $("equipment-notes-box").textContent = prep.equipment_text || "";
    $("fill-notes-box").textContent = prep.fill_notes || "";
    if (prep.audit_text) $("audit-text-box").textContent = prep.audit_text;

    renderPendingPartyAndProposals(prep);
    renderPendingList(prep.pending_lines || []);
    syncInputsFromState();
  }

  function renderPendingPartyAndProposals(prep) {
    const party = prep.party || state.snapshot.players || [];
    const cBox = $("pending-caster-select");
    const rBox = $("pending-recipient-select");
    cBox.innerHTML = "";
    rBox.innerHTML = "";
    party.forEach((p) => {
      const label = p.actor || p.name || p.style_label || String(p.actor_id);
      const o1 = document.createElement("option");
      o1.value = String(p.actor_id);
      o1.textContent = `施加者：${label}`;
      cBox.appendChild(o1);

      const o2 = document.createElement("option");
      o2.value = String(p.actor_id);
      o2.textContent = `受益者：${label}`;
      rBox.appendChild(o2);
    });
    if (prep.actor_id !== undefined) {
      cBox.value = String(prep.actor_id);
      rBox.value = String(prep.actor_id);
    }
    populateProposalsDropdown(prep.effect_proposals || []);
  }

  function populateProposalsDropdown(proposals) {
    state.proposals = proposals;
    const pBox = $("pending-proposal-select");
    pBox.innerHTML = "";
    if (!proposals.length) {
      const opt = document.createElement("option");
      opt.value = "-1";
      opt.textContent = "未读到支持的预选辅助效果";
      pBox.appendChild(opt);
      $("pending-effect-amount").value = "";
      return;
    }
    proposals.forEach((item, idx) => {
      const opt = document.createElement("option");
      opt.value = String(idx);
      const amt = item.preview_amount != null ? ` (${item.preview_amount.toFixed(2)}%)` : "";
      opt.textContent = `${item.title}${amt}`;
      pBox.appendChild(opt);
    });
    selectProposal(0);
  }

  function selectProposal(idx) {
    const item = state.proposals[idx];
    if (!item) return;
    $("pending-effect-amount").value = item.preview_amount != null ? Number(item.preview_amount.toFixed(4)) : "";
    const isFunnel = item.part && item.part.skill_type === "Funnel";
    $("pending-funnel-field").classList.toggle("hidden", !isFunnel);
    if (isFunnel && item.funnel_count) {
      $("pending-funnel-count").value = item.funnel_count;
    }
  }

  function renderPendingList(lines) {
    const ul = $("pending-effects-list");
    ul.innerHTML = "";
    lines.forEach((line, idx) => {
      const li = document.createElement("li");
      li.className = "tag-item";
      li.innerHTML = `<span>${line}</span><button type="button" class="btn btn-secondary btn-sm" data-rm-pending="${idx}">删除</button>`;
      ul.appendChild(li);
    });
    ul.querySelectorAll("[data-rm-pending]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const index = Number(btn.dataset.rmPending);
        try {
          const updated = await api("POST", "/damage/pending", {
            action: "remove",
            index,
            current_values: state.currentValues,
            current_hit_weights: state.hitWeights,
          });
          applyPendingUpdate(updated);
          await runCompute();
        } catch (err) {
          $("pending-status-msg").textContent = err.message;
        }
      });
    });
  }

  function applyPendingUpdate(updated) {
    if (updated.updates) {
      Object.entries(updated.updates).forEach(([k, v]) => {
        const formatted = Number(v.toPrecision(10)).toString();
        state.currentValues[k] = formatted;
        state.autofilledValues[k] = formatted;
      });
    }
    state.hpAdjustments = updated.hp_adjustments || state.hpAdjustments;
    if (updated.chain_changed) {
      state.hitWeights = updated.hit_weights_str || state.hitWeights;
      state.filledChain = updated.filled_chain;
      state.currentValues.chain_expression = updated.chain_expression;
      state.autofilledValues.chain_expression = updated.chain_expression;
      state.chainDirty = false;
    }
    renderPendingList(updated.pending_lines || []);
    $("pending-status-msg").textContent = updated.pending_status_text || "";
    syncInputsFromState();
  }

  // ---- Compute & Probability Plot Rendering ----
  async function runCompute() {
    const vals = { ...state.currentValues };
    delete vals.chain_expression;
    const overrides = {
      values: vals,
      params: state.params,
      flags: state.flags,
      pool: state.pool,
      damage_metric: state.damageMetric,
      use_skill: state.useSkill,
      damage_orb_enabled: state.damageOrbEnabled,
      use_destruction: state.useDestruction,
      use_dp_scaling: state.useDpScaling,
      sp_scaling: state.spScaling,
      sp_dr_scaling: state.spDrScaling,
      hit_weights: state.hitWeights,
      chain_expression: state.currentValues.chain_expression,
      chain_dirty: state.chainDirty,
      filled_chain: state.filledChain,
      hp_adjustments: state.hpAdjustments,
      shield_state: state.shieldState,
      auto_pool_blocked: state.autoPoolBlocked,
    };

    const res = await api("POST", "/damage/compute", { overrides });
    if (res.updated_values) {
      Object.entries(res.updated_values).forEach(([k, v]) => {
        if (k === "hit_weights") {
          state.hitWeights = v;
        } else {
          state.currentValues[k] = v;
        }
      });
    }
    state.chainDirty = !!res.chain_dirty;
    syncInputsFromState();
    renderComputeResult(res);
  }

  function renderComputeResult(res) {
    const errBanner = $("calc-error-banner");
    if (!res.ok) {
      errBanner.textContent = res.detail_text || "参数待补齐";
      errBanner.classList.remove("hidden");
    } else {
      errBanner.classList.add("hidden");
    }

    const pd = res.plot_data;
    state.plotData = pd;
    state.plotDamage = res.plot_damage ?? 1;

    const meanLabel = pd && pd.raw ? "平均打出伤害" : pd && pd.absolute ? "平均实际扣除" : "平均打出伤害";
    $("hero-mean-label").textContent = meanLabel;
    $("hero-mean-value").textContent = res.mean != null ? fmtNum(res.mean, 2) : res.damage != null ? fmtNum(res.damage, 2) : "—";
    $("hero-interval-value").textContent =
      res.low != null && res.high != null
        ? `中央 90% 浮动区间：${fmtNum(res.low, 2)} – ${fmtNum(res.high, 2)}`
        : res.prob_summary || "填入基础伤害与各 Hit 权重后生成区间";

    $("tile-base-damage").textContent = res.damage != null ? fmtNum(res.damage, 2) : "—";
    $("tile-destruction").textContent =
      res.destruction_start != null && res.destruction_end != null
        ? `${Number(res.destruction_start.toFixed(2))}% → ${Number(res.destruction_end.toFixed(2))}%`
        : "—";
    $("tile-kill-prob").textContent =
      res.kill_probability != null ? `${(res.kill_probability * 100).toFixed(2)}%` : "—";

    if (res.calculation_status) {
      $("calc-status-banner").textContent = res.calculation_status;
    }
    $("prob-summary-box").textContent = res.prob_summary || "";
    $("destruction-report-box").textContent = res.destruction_report || "尚无逐段明细";
    $("detail-text-box").textContent = res.detail_text || "";

    drawProbabilityCanvas();
  }

  function drawProbabilityCanvas(hoverX = null) {
    const canvas = $("prob-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(320, rect.width || 540);
    const h = Math.max(200, rect.height || 240);
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const style = getComputedStyle(document.documentElement);
    const colMuted = style.getPropertyValue("--muted").trim() || "#7c89ad";
    const colLine = style.getPropertyValue("--line-soft").trim() || "#1f2740";
    const colCyan = style.getPropertyValue("--cyan").trim() || "#5ce1e6";
    const colPink = style.getPropertyValue("--pink").trim() || "#ff7eb6";
    const colGold = style.getPropertyValue("--gold").trim() || "#f6c177";
    const colLav = style.getPropertyValue("--lavender").trim() || "#c4b5fd";

    const data = state.plotData;
    const l = 54, r = w - 20, t = 26, b = h - 32;
    if (!data || !data.x || !data.density || !data.density.length) {
      ctx.fillStyle = colMuted;
      ctx.font = "12px sans-serif";
      ctx.fillText("填入已确认的各 Hit 权重与基础伤害后显示浮动概率曲线", l, h / 2);
      ctx.restore();
      return;
    }

    const peak = Math.max(...data.density) || 1;
    const scale = state.plotDamage != null ? state.plotDamage : 1;
    const domain = data.domain || [0.9, 1.1];
    const xmin = domain[0], xmax = domain[1];
    const span = xmax - xmin || 1;

    ctx.strokeStyle = colLine;
    ctx.fillStyle = colMuted;
    ctx.font = "10px monospace";
    for (let i = 0; i <= 4; i++) {
      const y = b - ((b - t) * i) / 4;
      ctx.beginPath();
      ctx.moveTo(l, y);
      ctx.lineTo(r, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.fillText(((peak * i) / 4).toPrecision(2), l - 6, y + 3);
    }

    ctx.textAlign = "center";
    for (let i = 0; i <= 4; i++) {
      const x = l + ((r - l) * i) / 4;
      const factor = xmin + (span * i) / 4;
      ctx.fillText(Number((factor * scale).toPrecision(4)).toLocaleString(), x, b + 16);
    }

    // Area & line
    const step = data.absolute ? 1 : 4;
    const pts = [];
    for (let i = 0; i < data.x.length; i += step) {
      const xv = data.x[i];
      const yv = data.density[i];
      if (xv >= xmin && xv <= xmax) {
        const px = l + ((xv - xmin) / span) * (r - l);
        const py = b - (yv / peak) * (b - t);
        pts.push([px, py]);
      }
    }

    if (pts.length > 1) {
      ctx.beginPath();
      ctx.moveTo(pts[0][0], b);
      pts.forEach(([px, py]) => ctx.lineTo(px, py));
      ctx.lineTo(pts[pts.length - 1][0], b);
      ctx.closePath();
      ctx.fillStyle = "rgba(92, 225, 230, 0.16)";
      ctx.fill();

      ctx.beginPath();
      pts.forEach(([px, py], idx) => (idx === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)));
      ctx.strokeStyle = colCyan;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // 90% interval & mean vertical lines
    const markers = [
      [data.low, false],
      [data.mean !== undefined ? data.mean : 1, true],
      [data.high, false],
    ];
    ctx.save();
    ctx.setLineDash([4, 4]);
    markers.forEach(([val, isMean]) => {
      if (val === undefined || val === null) return;
      const px = l + ((val - xmin) / span) * (r - l);
      ctx.beginPath();
      ctx.moveTo(px, t);
      ctx.lineTo(px, b);
      ctx.strokeStyle = isMean ? colPink : colLav;
      ctx.lineWidth = isMean ? 1.8 : 1.2;
      ctx.stroke();
    });
    ctx.restore();

    // Point-mass atoms (gold lines)
    (data.atoms || []).forEach(([val, prob]) => {
      const px = l + ((val - xmin) / span) * (r - l);
      ctx.beginPath();
      ctx.moveTo(px, t);
      ctx.lineTo(px, b);
      ctx.strokeStyle = colGold;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = colGold;
      ctx.textAlign = "center";
      ctx.fillText(`${(prob * 100).toFixed(2)}%`, px, t - 4);
    });

    if (hoverX !== null && hoverX >= l && hoverX <= r) {
      const factor = xmin + ((hoverX - l) / (r - l)) * span;
      const idx = Math.max(0, Math.min(data.x.length - 1, Math.round((factor - data.x[0]) / data.step)));
      const dens = data.density[idx] || 0;
      const py = b - (dens / peak) * (b - t);
      ctx.beginPath();
      ctx.arc(hoverX, py, 4, 0, Math.PI * 2);
      ctx.fillStyle = colPink;
      ctx.fill();
      $("plot-hover-hint").textContent = `${data.absolute ? "伤害" : "倍率"} ${factor.toFixed(4)} · 对应伤害 ${fmtNum(
        factor * scale,
        2
      )} · 概率密度 ${dens.toPrecision(3)}`;
    }
    ctx.restore();
  }

  // ---- Damage Sequence (3-step) ----
  async function runSequence(action) {
    try {
      const vals = { ...state.currentValues };
      delete vals.chain_expression;
      const res = await api("POST", "/damage/sequence", {
        action,
        overrides: {
          values: vals,
          params: state.params,
          flags: state.flags,
          pool: state.pool,
          damage_metric: state.damageMetric,
          use_skill: state.useSkill,
          damage_orb_enabled: state.damageOrbEnabled,
          use_destruction: state.useDestruction,
          use_dp_scaling: state.useDpScaling,
          sp_scaling: state.spScaling,
          sp_dr_scaling: state.spDrScaling,
          hit_weights: state.hitWeights,
          chain_expression: state.currentValues.chain_expression,
          chain_dirty: state.chainDirty,
          filled_chain: state.filledChain,
          hp_adjustments: state.hpAdjustments,
          shield_state: state.shieldState,
          auto_pool_blocked: state.autoPoolBlocked,
        },
      });
      $("seq-message").textContent = res.message || "";
      renderSequenceSteps(res.steps || []);
      if (action === "undo" || action === "clear") {
        await runPrepare();
      }
    } catch (err) {
      $("seq-message").textContent = err.message;
    }
  }

  function renderSequenceSteps(steps) {
    const box = $("seq-steps-list");
    box.innerHTML = "";
    steps.forEach((s, i) => {
      const div = document.createElement("div");
      div.className = "seq-step-card";
      div.innerHTML = `
        <strong>第 ${i + 1} 步 · ${s.actor} · ${s.skill}</strong>
        <div>打出伤害 ${fmtNum(s.raw_damage, 2)} · 实际扣除 ${fmtNum(s.damage, 2)}</div>
        <div class="hint">DP ${fmtNum(s.before.dp, 0)} → ${fmtNum(s.after.dp, 0)} ｜ HP ${fmtNum(
        s.before.hp,
        0
      )} → ${fmtNum(s.after.hp, 0)} ｜ 破坏率 ${Number(s.before.rate.toFixed(2))}% → ${Number(
        s.after.rate.toFixed(2)
      )}%</div>
      `;
      box.appendChild(div);
    });
  }

  // ---- Offline Team & Shareable Calculation Plan (B3 / F3) ----
  async function loadTeamsArchive() {
    const q = $("team-search-input") ? $("team-search-input").value.trim() : "";
    const scope = $("team-search-scope") ? $("team-search-scope").value : "team";
    const data = await api("GET", `/teams?q=${encodeURIComponent(q)}&scope=${encodeURIComponent(scope)}`);
    state.teams = data.teams || [];
    state.drafts = data.drafts || [];
    renderArchiveSidebar();
    populateOfflineTeamSelector();
  }

  function populateOfflineTeamSelector() {
    const sel = $("offline-team-select");
    const old = sel.value;
    sel.innerHTML = "";
    const all = [...state.teams, ...state.drafts];
    if (state.offlineTeamRecord && !all.some((r) => r.key === state.offlineTeamRecord.key)) {
      all.unshift(state.offlineTeamRecord);
    }
    if (!all.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "暂无配队档案（可导入试算方案 JSON）";
      sel.appendChild(opt);
      return;
    }
    all.forEach((rec) => {
      const opt = document.createElement("option");
      opt.value = rec.key;
      opt.textContent = (rec.draft ? "待确认 · " : "") + rec.name;
      sel.appendChild(opt);
    });
    if (old && [...sel.options].some((o) => o.value === old)) {
      sel.value = old;
    }
    selectOfflineTeam(sel.value);
  }

  function selectOfflineTeam(key) {
    const all = [...state.teams, ...state.drafts];
    if (state.offlineTeamRecord) all.unshift(state.offlineTeamRecord);
    const found = all.find((r) => r.key === key) || all[0];
    if (!found) return;
    state.offlineTeamRecord = found;
    renderOfflineMemberSkills(found.payload);
    syncOfflineStatusTargets(found.payload);
  }

  function renderOfflineMemberSkills(payload) {
    const container = $("offline-members-skills");
    container.innerHTML = "";
    const members = (payload && payload.members) || [];
    members.forEach((m, idx) => {
      const row = document.createElement("div");
      row.className = "form-row";
      const pos = [0, 1, 2].includes(m.position) ? "前排" : "后排";
      const title = `${pos} · ${m.actor || "?"}（${m.style_name || m.style_label}）`;
      const sel = document.createElement("select");
      sel.className = "input-select";
      const skills = m.skills_enriched || m.skills || [];
      skills.forEach((sk, si) => {
        const forms = sk.forms || [];
        const lv = sk.level ?? "?";
        if (!forms.length) {
          const opt = document.createElement("option");
          opt.value = JSON.stringify([si, null]);
          opt.textContent = `${sk.name || sk.label} Lv.${lv}`;
          sel.appendChild(opt);
        } else {
          forms.forEach((f) => {
            const opt = document.createElement("option");
            opt.value = JSON.stringify([si, f.form_index]);
            opt.textContent = `${sk.name || sk.label} ⇄ 形态${f.form_index + 1}「${f.name}」 Lv.${lv}`;
            sel.appendChild(opt);
          });
        }
      });
      const existing = state.offlineSkillChoices[idx];
      if (existing) {
        const str = JSON.stringify(existing);
        if ([...sel.options].some((o) => o.value === str)) sel.value = str;
      }
      state.offlineSkillChoices[idx] = sel.value ? JSON.parse(sel.value) : [0, null];
      sel.addEventListener("change", () => {
        state.offlineSkillChoices[idx] = JSON.parse(sel.value);
      });
      row.innerHTML = `<label>${title}</label>`;
      row.appendChild(sel);
      container.appendChild(row);
    });
  }

  function syncOfflineStatusTargets(payload) {
    const kindOpt = $("off-status-kind").selectedOptions[0];
    const side = kindOpt ? kindOpt.dataset.side : "player";
    const tBox = $("off-status-target");
    tBox.innerHTML = "";
    if (side === "enemy") {
      const opt = document.createElement("option");
      opt.value = "enemy";
      opt.textContent = "敌人";
      tBox.appendChild(opt);
      return;
    }
    const allOpt = document.createElement("option");
    allOpt.value = "all";
    allOpt.textContent = "我方全体";
    tBox.appendChild(allOpt);
    const members = ((payload || (state.offlineTeamRecord && state.offlineTeamRecord.payload)) || {}).members || [];
    members.forEach((m, idx) => {
      const opt = document.createElement("option");
      opt.value = String(idx);
      opt.textContent = `我方 · ${m.actor || m.style_label}`;
      tBox.appendChild(opt);
    });
  }

  function renderOfflineManualStatuses() {
    const ul = $("off-status-list");
    ul.innerHTML = "";
    const members = ((state.offlineTeamRecord && state.offlineTeamRecord.payload) || {}).members || [];
    state.offlineStatuses.forEach((entry, idx) => {
      let targetLabel = "我方全体";
      if (entry.target === "enemy") targetLabel = "敌人";
      else if (typeof entry.target === "number" || /^\d+$/.test(String(entry.target))) {
        const m = members[Number(entry.target)];
        targetLabel = `我方 · ${m ? m.actor || m.style_label : entry.target}`;
      }
      const li = document.createElement("li");
      li.className = "tag-item";
      li.innerHTML = `<span>${targetLabel} ← ${entry.description || entry.status.name}</span><button type="button" class="btn btn-secondary btn-sm" data-rm-off-st="${idx}">删除</button>`;
      ul.appendChild(li);
    });
    ul.querySelectorAll("[data-rm-off-st]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.offlineStatuses.splice(Number(btn.dataset.rmOffSt), 1);
        renderOfflineManualStatuses();
      });
    });
  }

  function buildOfflinePlanPayload() {
    const rec = state.offlineTeamRecord;
    if (!rec || !rec.payload) {
      throw new Error("请先选择配队档案或导入试算方案");
    }
    const rates = {};
    document.querySelectorAll("#off-enemy-rates [data-rate]").forEach((inp) => {
      const v = inp.value.trim();
      rates[inp.dataset.rate] = v === "" ? null : Number(v);
    });
    const coef = $("off-enemy-coef").value.trim();
    const maxDr = $("off-enemy-max").value.trim();
    const bonus = $("off-field-bonus").value.trim();
    return {
      schema: 1,
      kind: "hbr_offline_plan",
      title: rec.name || "离线试算方案",
      team: rec.payload,
      skill_choices: state.offlineSkillChoices,
      enemy: {
        name: $("off-enemy-name").value.trim() || "自定义敌人",
        dp: Number($("off-enemy-dp").value || 0),
        hp: Number($("off-enemy-hp").value || 1000000),
        defense: state.enemyStatOverride,
        damage_rate: Number($("off-enemy-dr-rate").value || 100),
        destruction_coefficient: coef === "" ? null : Number(coef),
        destruction_max: maxDr === "" ? null : Number(maxDr),
        rates,
        down: $("off-enemy-down").checked ? 1 : 0,
      },
      field: {
        element: $("off-field-element").value,
        bonus: bonus === "" ? null : Number(bonus),
      },
      od_level: Number($("off-od-level").value || 0),
      manual_statuses: state.offlineStatuses.map((x) => ({
        target: x.target,
        status: x.status,
      })),
      selected_actor_index: Math.max(0, $("live-player-select").selectedIndex),
      mode_options: {
        transcend: $("mode-transcend").value,
        transcend_element: $("mode-transcend-el").value,
        high_boost: $("mode-high-boost").value,
      },
    };
  }

  async function applyOfflineSetup() {
    try {
      const payload = buildOfflinePlanPayload();
      const res = await api("POST", "/offline/plan", payload);
      $("offline-setup-msg").textContent = "已应用离线试算配置并生成快照。";
      await loadSnapshot(true);
    } catch (err) {
      $("offline-setup-msg").textContent = `错误：${err.message}`;
    }
  }

  // ---- Archive View (F3) ----
  function renderArchiveSidebar() {
    const dList = $("archive-drafts-list");
    const tList = $("archive-teams-list");
    const overwriteSel = $("draft-overwrite-target");
    dList.innerHTML = "";
    tList.innerHTML = "";
    overwriteSel.innerHTML = '<option value="">另存为新配队</option>';

    state.teams.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = String(t.id);
      opt.textContent = `覆盖：${t.name} (#${t.id})`;
      overwriteSel.appendChild(opt);
    });

    if (!state.drafts.length) {
      dList.innerHTML = '<li class="hint">暂无待确认战斗记录</li>';
    }
    state.drafts.forEach((d) => {
      const li = document.createElement("li");
      li.className = `archive-item ${
        state.selectedArchiveRecord && state.selectedArchiveRecord.key === d.key ? "active" : ""
      }`;
      li.innerHTML = `<span>待确认 · ${d.name}</span><span class="badge badge-gold">Draft</span>`;
      li.addEventListener("click", () => selectArchiveRecord(d));
      dList.appendChild(li);
    });

    if (!state.teams.length) {
      tList.innerHTML = '<li class="hint">暂无已保存配队</li>';
    }
    state.teams.forEach((t) => {
      const li = document.createElement("li");
      li.className = `archive-item ${
        state.selectedArchiveRecord && state.selectedArchiveRecord.key === t.key ? "active" : ""
      }`;
      li.innerHTML = `<span>${t.name}</span><span class="badge">#${t.id}</span>`;
      li.addEventListener("click", () => selectArchiveRecord(t));
      tList.appendChild(li);
    });

    if (!state.selectedArchiveRecord && (state.teams.length || state.drafts.length)) {
      selectArchiveRecord(state.teams[0] || state.drafts[0]);
    } else if (state.selectedArchiveRecord) {
      const refreshed = [...state.teams, ...state.drafts].find((r) => r.key === state.selectedArchiveRecord.key);
      if (refreshed) selectArchiveRecord(refreshed);
    }
  }

  function selectArchiveRecord(rec) {
    state.selectedArchiveRecord = rec;
    $("archive-team-title").textContent = (rec.draft ? "待确认战斗记录 · " : "") + rec.name;
    const turn = rec.payload && rec.payload.context && rec.payload.context.turn;
    $("archive-team-meta").textContent = `采样时间：${(rec.captured_at || "未知").replace("T", " ")} · 采样回合：Turn ${
      turn ?? "?"
    }`;
    $("btn-use-team-in-calc").disabled = false;
    $("btn-delete-team").disabled = false;
    $("draft-save-bar").classList.toggle("hidden", !rec.draft);

    const grid = $("archive-members-grid");
    grid.innerHTML = "";
    const members = (rec.payload && rec.payload.members) || [];
    members.forEach((m) => {
      const card = document.createElement("article");
      card.className = "member-card";
      const posBadge = [0, 1, 2].includes(m.position) ? "前排" : "后排";
      const statsHtml = STAT_LABELS.map(
        ([k, lbl]) => `<div class="stat-cell"><span>${lbl}</span><strong>${(m.stats && m.stats[k]) ?? "—"}</strong></div>`
      ).join("");

      const skills = m.skills_enriched || m.skills || [];
      const skillsHtml = skills
        .map((sk) => {
          const formsText =
            sk.forms && sk.forms.length
              ? ` <span class="badge">⇄ ${sk.forms.map((f) => f.name).join(" / ")}</span>`
              : "";
          return `
            <div class="skill-chip">
              <span><strong>${sk.name || sk.label}</strong> <span class="hint">Lv.${sk.level ?? "?"}</span>${formsText}</span>
              <button type="button" class="btn btn-secondary btn-sm" data-show-skill="${sk.label}" data-skill-lv="${
            sk.level ?? "?"
          }">查看详情</button>
            </div>
          `;
        })
        .join("");

      const passives = m.passives_enriched || m.passives || [];
      const accessories = passives.filter((p) => p.group === "饰品效果");
      const resonance = passives.filter((p) => p.group === "共鸣被动");
      const talents = passives.filter((p) => p.group !== "饰品效果" && p.group !== "共鸣被动");

      const renderPassiveGroup = (items) =>
        items.length
          ? items
              .map(
                (p) =>
                  `<div class="tag-item"><span>${p.slot ? `<span class="badge">${p.slot}</span> ` : ""}<strong>${
                    p.name || p.label
                  }</strong> <span class="hint">${p.description || ""}</span></span></div>`
              )
              .join("")
          : '<p class="hint">无记录</p>';

      card.innerHTML = `
        <div class="member-top">
          <div class="avatar-box">
            <img src="/portrait/${encodeURIComponent(m.style_label || "")}" alt="${m.actor || ""}" onerror="this.remove()" />
            <span>${(m.actor || "?").slice(0, 2)}</span>
          </div>
          <div>
            <h3>${m.actor || "未知角色"} · ${m.style_name || m.style_label}</h3>
            <p class="hint"><span class="badge">${posBadge}</span> 风格标识：${m.style_label} ｜ DP ${m.dp ?? "?"}/${
        m.dp_max ?? "?"
      } · HP ${m.hp ?? "?"}/${m.hp_max ?? "?"}</p>
          </div>
        </div>
        <div class="stats-6-grid">${statsHtml}</div>
        <div>
          <h4 class="section-sub">已读取装备指令技能</h4>
          <div class="skill-chip-list">${skillsHtml || '<p class="hint">未读取到技能</p>'}</div>
        </div>
        <details class="fold">
          <summary>饰品效果 (${accessories.length}) · 共鸣 (${resonance.length}) · 天赋被动 (${talents.length})</summary>
          <div class="fold-body">
            <h5 class="section-sub">饰品效果</h5>
            ${renderPassiveGroup(accessories)}
            <h5 class="section-sub mt-8">共鸣被动</h5>
            ${renderPassiveGroup(resonance)}
            <h5 class="section-sub mt-8">天赋与其他被动</h5>
            ${renderPassiveGroup(talents)}
          </div>
        </details>
      `;
      grid.appendChild(card);
    });

    grid.querySelectorAll("[data-show-skill]").forEach((btn) => {
      btn.addEventListener("click", () => openSkillModal(btn.dataset.showSkill, btn.dataset.skillLv));
    });
  }

  async function openSkillModal(label, level) {
    const modal = $("skill-modal");
    const title = $("skill-modal-title");
    const body = $("skill-modal-body");
    modal.classList.remove("hidden");
    title.textContent = `技能详情 · ${label} (档案等级 Lv.${level})`;
    body.innerHTML = '<p class="hint">正在查询本地资料库…</p>';
    const data = await api("GET", `/skills/detail?label=${encodeURIComponent(label)}`);
    if (!data.found) {
      body.innerHTML = `<div class="card"><p>暂无可唯一匹配的技能资料（标识：${label}）。</p><p class="hint">不会使用同名技能替代当前变体。</p></div>`;
      return;
    }
    const renderDetailCard = (d, subtitle = "") => {
      const effectsHtml = (d.effects || [])
        .map(
          (ef) => `
          <div class="tag-item" style="flex-direction:column;align-items:flex-start;">
            <div><strong>${ef.kind || "效果"}</strong> ${
            ef.elements && ef.elements.length ? `[${ef.elements.join("/")}]` : ""
          } ${ef.physical_type || ""} ${ef.condition ? `<span class="badge badge-gold">${ef.condition}</span>` : ""}</div>
            <div class="hint">基础威力：${(ef.power || []).join(" – ") || "—"} ｜ 满额差值：${
            ef.stat_difference ?? "—"
          } ｜ DP×${ef.dp_multiplier ?? 1} / HP×${ef.hp_multiplier ?? 1} / 破坏×${ef.destruction_multiplier ?? 1}</div>
          </div>
        `
        )
        .join("");
      return `
        <div class="card">
          <h3>${subtitle}${d.name} <span class="badge">SP ${d.sp_cost ?? "?"}</span> <span class="badge">${
        d.hit_count ?? "?"
      } Hit</span></h3>
          <p class="hint mt-4">${d.description || ""}</p>
          <div class="tag-list mt-8">${effectsHtml}</div>
        </div>
      `;
    };
    let html = renderDetailCard(data.detail);
    (data.forms || []).forEach((f) => {
      html += renderDetailCard(f.detail, `⇄ 形态 ${f.index + 1} · `);
    });
    body.innerHTML = html;
  }

  // ---- Reference Library View (F5) ----
  async function searchLibrary() {
    const region = $("lib-region").value;
    const dataset = $("lib-dataset").value;
    const q = $("lib-query").value.trim();
    const res = await api(
      "GET",
      `/library/search?region=${encodeURIComponent(region)}&dataset=${encodeURIComponent(dataset)}&q=${encodeURIComponent(q)}`
    );
    const ul = $("lib-results-list");
    ul.innerHTML = "";
    if (!res.available) {
      $("lib-status").textContent = "本地资料库尚未同步（可在桌面端星屑资料室点击同步）。";
      return;
    }
    $("lib-status").textContent = `找到 ${res.rows.length} 条记录${res.truncated ? "（已截断）" : ""}`;
    res.rows.forEach((row) => {
      const li = document.createElement("li");
      li.className = "archive-item";
      li.innerHTML = `<span>${row.name || row.label}</span><span class="hint">${row.label}</span>`;
      li.addEventListener("click", () => loadLibraryRecord(row.record_key));
      ul.appendChild(li);
    });
  }

  async function loadLibraryRecord(key) {
    const res = await api("GET", `/library/record?key=${encodeURIComponent(key)}`);
    const rec = res.record;
    $("lib-detail-title").textContent = `${rec.name} (${rec.dataset} · ${rec.region})`;
    const skillsHtml = (rec.skills || [])
      .map(
        (s) =>
          `<div class="skill-chip"><span><strong>${s.name}</strong> (SP ${s.sp_cost ?? "?"} · ${
            s.hit_count ?? "?"
          } Hit)<br/><span class="hint">${s.description || ""}</span></span></div>`
      )
      .join("");
    $("lib-detail-body").innerHTML = `
      ${skillsHtml ? `<h4 class="section-sub">关联技能 (${rec.skills.length})</h4><div class="skill-chip-list mb-8">${skillsHtml}</div>` : ""}
      <h4 class="section-sub">原始结构化 JSON</h4>
      <pre class="code-box">${JSON.stringify(rec.raw, null, 2)}</pre>
    `;
  }

  async function runLibrarySql() {
    const sql = $("lib-sql-input").value.trim();
    const out = $("lib-sql-output");
    try {
      const res = await api("POST", "/library/sql", { sql });
      const ths = (res.columns || []).map((c) => `<th>${c}</th>`).join("");
      const trs = (res.rows || [])
        .map((r) => `<tr>${r.map((cell) => `<td>${cell ?? ""}</td>`).join("")}</tr>`)
        .join("");
      out.innerHTML = `<table class="sql-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
    } catch (err) {
      out.innerHTML = `<div class="error-banner">${err.message}</div>`;
    }
  }

  // ---- Navigation & Event Bindings ----
  function switchView(viewName) {
    document.querySelectorAll(".nav-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.view === viewName);
    });
    ["calc", "teams", "library"].forEach((v) => {
      $(`view-${v}`).classList.toggle("hidden", v !== viewName);
    });
    if (viewName === "teams") loadTeamsArchive();
    if (viewName === "library") searchLibrary();
  }

  function switchSourceMode(mode) {
    state.mode = mode;
    document.querySelectorAll("#source-mode-seg .seg-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === mode);
    });
    $("live-settings-panel").classList.toggle("hidden", mode !== "live");
    $("offline-settings-panel").classList.toggle("hidden", mode !== "offline");
    api("POST", "/mode", { mode }).then(() => {
      if (mode === "offline") {
        loadTeamsArchive().then(() => applyOfflineSetup());
      } else {
        loadSnapshot(true);
      }
    });
  }

  function bindEvents() {
    document.querySelectorAll(".nav-tab").forEach((btn) => {
      btn.addEventListener("click", () => switchView(btn.dataset.view));
    });

    $("theme-select").addEventListener("change", (e) => {
      document.documentElement.setAttribute("data-theme", e.target.value);
      drawProbabilityCanvas();
    });

    $("btn-top-compute").addEventListener("click", () => runCompute());

    document.querySelectorAll("#source-mode-seg .seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchSourceMode(btn.dataset.mode));
    });

    $("btn-refresh-snapshot").addEventListener("click", () => loadSnapshot(false));
    $("btn-autofill").addEventListener("click", () => runPrepare());
    $("live-player-select").addEventListener("change", () => runPrepare());
    $("live-enemy-select").addEventListener("change", () => runPrepare());
    $("btn-next-actor").addEventListener("click", () => {
      const sel = $("live-player-select");
      if (sel.options.length) {
        sel.selectedIndex = (sel.selectedIndex + 1) % sel.options.length;
        runPrepare();
      }
    });

    // Boss stat, skill form, mode options
    $("shared-enemy-stat").addEventListener("change", () => {
      const v = $("shared-enemy-stat").value.trim();
      state.enemyStatOverride = v === "" ? null : Number(v);
      state.params.enemy = v;
      if (state.snapshot.connected) runPrepare();
      else runCompute();
    });

    $("btn-reset-enemy-stat").addEventListener("click", () => {
      state.enemyStatOverride = null;
      $("shared-enemy-stat").value = "";
      if (state.snapshot.connected) runPrepare();
      else runCompute();
    });

    $("skill-form-select").addEventListener("change", () => runPrepare());
    ["mode-transcend", "mode-transcend-el", "mode-high-boost"].forEach((id) => {
      $(id).addEventListener("change", () => runPrepare());
    });

    // Pending effects
    $("pending-caster-select").addEventListener("change", async () => {
      const res = await api("POST", "/damage/effect/proposals", {
        caster_id: $("pending-caster-select").value,
      });
      populateProposalsDropdown(res.proposals || []);
    });
    $("pending-proposal-select").addEventListener("change", (e) => {
      selectProposal(Number(e.target.value));
    });
    $("btn-precast-support").addEventListener("click", async () => {
      try {
        const res = await api("POST", "/damage/precast", {
          caster_id: $("pending-caster-select").value,
          options: currentOptions(),
        });
        applyPreparedToState(res);
        $("pending-status-msg").textContent = res.precast_message || "";
        await runCompute();
      } catch (err) {
        $("pending-status-msg").textContent = err.message;
      }
    });
    $("btn-add-pending").addEventListener("click", async () => {
      try {
        const pIdx = Number($("pending-proposal-select").value);
        if (pIdx < 0) throw new Error("请先选择可预添加的技能效果");
        const updated = await api("POST", "/damage/pending", {
          action: "add",
          caster_id: $("pending-caster-select").value,
          proposal_index: pIdx,
          recipient_id: $("pending-recipient-select").value,
          amount: Number($("pending-effect-amount").value || 0),
          funnel_count: Number($("pending-funnel-count").value || 3),
          current_values: state.currentValues,
          current_hit_weights: state.hitWeights,
        });
        applyPendingUpdate(updated);
        await runCompute();
      } catch (err) {
        $("pending-status-msg").textContent = err.message;
      }
    });

    // Pool, metric, flags, reset overrides
    document.querySelectorAll("#pool-seg .seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.pool = btn.dataset.pool;
        syncInputsFromState();
        runCompute();
      });
    });
    document.querySelectorAll("#metric-seg .seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.damageMetric = btn.dataset.metric;
        syncInputsFromState();
        runCompute();
      });
    });
    ["critical", "penetration_critical", "absorbed"].forEach((k) => {
      $(`flag-${k}`).addEventListener("change", (e) => {
        state.flags[k] = e.target.checked;
        runCompute();
      });
    });
    $("btn-reset-all-overrides").addEventListener("click", () => {
      state.currentValues = { ...state.autofilledValues };
      state.chainDirty = true;
      syncInputsFromState();
      runCompute();
    });

    // Drawers & toggles
    document.querySelectorAll("#drawer-tabs .subtab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("#drawer-tabs .subtab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const target = tab.dataset.drawer;
        ["destruction", "skill", "equipment", "audit"].forEach((d) => {
          $(`drawer-${d}`).classList.toggle("hidden", d !== target);
        });
      });
    });

    $("input-hit-weights").addEventListener("change", (e) => {
      state.hitWeights = e.target.value;
      runCompute();
    });
    $("toggle-use-destruction").addEventListener("change", (e) => {
      state.useDestruction = e.target.checked;
      runCompute();
    });
    $("toggle-use-skill").addEventListener("change", (e) => {
      state.useSkill = e.target.checked;
      runCompute();
    });
    $("toggle-damage-orb").addEventListener("change", (e) => {
      state.damageOrbEnabled = e.target.checked;
      runCompute();
    });
    $("toggle-dp-scaling").addEventListener("change", (e) => {
      state.useDpScaling = e.target.checked;
      runCompute();
    });
    $("toggle-sp-dr-scaling").addEventListener("change", (e) => {
      state.spDrScaling = e.target.checked;
      runCompute();
    });

    // Sequence buttons
    $("btn-seq-add").addEventListener("click", () => runSequence("add"));
    $("btn-seq-undo").addEventListener("click", () => runSequence("undo"));
    $("btn-seq-clear").addEventListener("click", () => runSequence("clear"));

    // Plot hover
    const canvas = $("prob-canvas");
    canvas.addEventListener("mousemove", (e) => {
      const rect = canvas.getBoundingClientRect();
      drawProbabilityCanvas(e.clientX - rect.left);
    });
    canvas.addEventListener("mouseleave", () => drawProbabilityCanvas(null));
    window.addEventListener("resize", () => drawProbabilityCanvas(null));

    // Offline controls
    $("offline-team-select").addEventListener("change", (e) => {
      state.offlineSkillChoices = {};
      selectOfflineTeam(e.target.value);
    });
    $("btn-offline-reload-teams").addEventListener("click", () => loadTeamsArchive());
    $("off-status-kind").addEventListener("change", () => syncOfflineStatusTargets());
    $("btn-off-add-status").addEventListener("click", async () => {
      try {
        const res = await api("POST", "/offline/status", {
          kind: $("off-status-kind").value,
          target: $("off-status-target").value,
          element: $("off-status-element").value,
          value: $("off-status-value").value,
          count: $("off-status-count").value || null,
          permanent: $("off-status-perm").checked,
        });
        const t = /^\d+$/.test(String(res.target)) ? Number(res.target) : res.target;
        state.offlineStatuses.push({ target: t, status: res.status, description: res.description });
        renderOfflineManualStatuses();
      } catch (err) {
        $("offline-setup-msg").textContent = err.message;
      }
    });
    $("btn-off-clear-status").addEventListener("click", () => {
      state.offlineStatuses = [];
      renderOfflineManualStatuses();
    });
    $("btn-apply-offline").addEventListener("click", () => applyOfflineSetup());

    // Export / Import shareable calculation plan JSON (B3)
    $("btn-export-plan").addEventListener("click", async () => {
      try {
        const payload = buildOfflinePlanPayload();
        const res = await api("POST", "/offline/plan", { ...payload, activate: false });
        const blob = new Blob([JSON.stringify(res.plan, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${(res.plan.title || "hbr-offline-plan").replace(/[\\/:*?"<>|]/g, "_")}.json`;
        a.click();
        URL.revokeObjectURL(url);
        $("offline-setup-msg").textContent = "已导出试算方案 JSON（已自动剥离个人对局 ID 与内存地址）。";
      } catch (err) {
        $("offline-setup-msg").textContent = `导出失败：${err.message}`;
      }
    });

    $("input-import-plan").addEventListener("change", async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const plan = JSON.parse(text);
        const res = await api("POST", "/offline/plan", { ...plan, activate: true });
        const importedRec = {
          key: "imported:plan",
          draft: false,
          name: res.plan.title || "导入试算方案",
          payload: res.team_enriched || res.plan.team,
        };
        state.offlineTeamRecord = importedRec;
        state.offlineSkillChoices = {};
        Object.entries(res.plan.skill_choices || {}).forEach(([k, v]) => {
          state.offlineSkillChoices[Number(k)] = v;
        });
        const ec = res.plan.enemy || {};
        $("off-enemy-name").value = ec.name || "自定义敌人";
        $("off-enemy-dp").value = ec.dp ?? 0;
        $("off-enemy-hp").value = ec.hp ?? 1000000;
        $("off-enemy-dr-rate").value = ec.damage_rate ?? 100;
        $("off-enemy-coef").value = ec.destruction_coefficient ?? "";
        $("off-enemy-max").value = ec.destruction_max ?? "";
        $("off-enemy-down").checked = !!ec.down;
        document.querySelectorAll("#off-enemy-rates [data-rate]").forEach((inp) => {
          const r = (ec.rates || {})[inp.dataset.rate];
          inp.value = r != null ? r : 100;
        });
        const fc = res.plan.field || {};
        $("off-field-element").value = fc.element || "";
        $("off-field-bonus").value = fc.bonus ?? "";
        $("off-od-level").value = String(res.plan.od_level ?? 0);
        state.enemyStatOverride = ec.defense ?? null;
        $("shared-enemy-stat").value = state.enemyStatOverride ?? "";
        state.offlineStatuses = (res.plan.manual_statuses || []).map((x) => ({
          target: x.target,
          status: x.status,
          description: x.status.name,
        }));
        populateOfflineTeamSelector();
        $("offline-team-select").value = importedRec.key;
        renderOfflineMemberSkills(importedRec.payload);
        renderOfflineManualStatuses();
        $("offline-setup-msg").textContent = `已导入试算方案：${importedRec.name}`;
        await loadSnapshot(true);
      } catch (err) {
        $("offline-setup-msg").textContent = `导入失败：${err.message}`;
      } finally {
        e.target.value = "";
      }
    });

    // Archive View bindings
    $("btn-teams-refresh").addEventListener("click", () => loadTeamsArchive());
    $("team-search-input").addEventListener("input", () => loadTeamsArchive());
    $("team-search-scope").addEventListener("change", () => loadTeamsArchive());
    $("btn-save-draft").addEventListener("click", async () => {
      const rec = state.selectedArchiveRecord;
      if (!rec || !rec.draft) return;
      try {
        const name = $("draft-save-name").value.trim();
        const target = $("draft-overwrite-target").value;
        await api("POST", "/teams/save", { run_id: rec.run_id, name, target });
        $("draft-save-name").value = "";
        state.selectedArchiveRecord = null;
        await loadTeamsArchive();
      } catch (err) {
        alert(err.message);
      }
    });
    $("btn-delete-team").addEventListener("click", async () => {
      const rec = state.selectedArchiveRecord;
      if (!rec) return;
      await api("POST", "/teams/delete", {
        key: rec.draft ? rec.run_id : rec.id,
        draft: rec.draft,
      });
      state.selectedArchiveRecord = null;
      await loadTeamsArchive();
    });
    $("btn-use-team-in-calc").addEventListener("click", () => {
      const rec = state.selectedArchiveRecord;
      if (!rec) return;
      state.offlineTeamRecord = rec;
      state.offlineSkillChoices = {};
      switchView("calc");
      switchSourceMode("offline");
    });

    // Library View bindings
    $("btn-lib-search").addEventListener("click", () => searchLibrary());
    $("lib-query").addEventListener("keydown", (e) => {
      if (e.key === "Enter") searchLibrary();
    });
    $("btn-run-sql").addEventListener("click", () => runLibrarySql());

    // Modal close
    $("btn-close-skill-modal").addEventListener("click", () => $("skill-modal").classList.add("hidden"));
    $("skill-modal").addEventListener("click", (e) => {
      if (e.target === $("skill-modal")) $("skill-modal").classList.add("hidden");
    });
  }

  // ---- Init ----
  function init() {
    buildMultiplierDOM();
    syncInputsFromState();
    bindEvents();
    const hash = window.location.hash.replace("#", "");
    if (["calc", "teams", "library"].includes(hash)) {
      switchView(hash);
    }
    loadTeamsArchive();
    loadSnapshot(true);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
