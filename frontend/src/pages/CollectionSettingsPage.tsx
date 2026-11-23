import { useEffect, useState } from "react";
import { CalendarClock, Check, Clock3, Save } from "lucide-react";
import { api, type CollectionSchedule, type TrendingPeriod } from "../services/api";

interface ScheduleForm {
  enabled: boolean;
  time: string;
  timezone: string;
  weekday: number;
  day_of_month: number;
}

const defaults: Record<TrendingPeriod, ScheduleForm> = {
  daily: { enabled: false, time: "09:00", timezone: "Asia/Shanghai", weekday: 0, day_of_month: 1 },
  weekly: { enabled: false, time: "09:00", timezone: "Asia/Shanghai", weekday: 0, day_of_month: 1 },
  monthly: { enabled: false, time: "09:00", timezone: "Asia/Shanghai", weekday: 0, day_of_month: 1 },
};

const periods: { value: TrendingPeriod; title: string; subtitle: string }[] = [
  { value: "daily", title: "日榜采集", subtitle: "每天按指定时间采集一次" },
  { value: "weekly", title: "周榜采集", subtitle: "每周指定星期按指定时间采集" },
  { value: "monthly", title: "月榜采集", subtitle: "每月指定日期按指定时间采集" },
];

const timezones = [
  { value: "Asia/Shanghai", label: "中国标准时间 · Asia/Shanghai" },
  { value: "Asia/Tokyo", label: "日本标准时间 · Asia/Tokyo" },
  { value: "UTC", label: "协调世界时 · UTC" },
  { value: "America/Los_Angeles", label: "美国太平洋时间 · America/Los_Angeles" },
  { value: "Europe/London", label: "英国时间 · Europe/London" },
];

const weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"];

function formatDate(value: string | null, timezone: string): string {
  return value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false, timeZone: timezone })
    : "未安排";
}

function toForm(schedule: CollectionSchedule): ScheduleForm {
  return {
    enabled: schedule.enabled,
    time: schedule.settings.time ?? "09:00",
    timezone: schedule.timezone || "Asia/Shanghai",
    weekday: schedule.settings.weekday ?? 0,
    day_of_month: schedule.settings.day_of_month ?? 1,
  };
}

export default function CollectionSettingsPage() {
  const [forms, setForms] = useState<Record<TrendingPeriod, ScheduleForm>>(defaults);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<TrendingPeriod | null>(null);
  const [schedules, setSchedules] = useState<CollectionSchedule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savedPeriod, setSavedPeriod] = useState<TrendingPeriod | null>(null);

  useEffect(() => {
    api.collectionSchedules()
      .then((response) => {
        setSchedules(response.items);
        setForms((current) => {
          const next = { ...current };
          for (const schedule of response.items) {
            const period = schedule.job_type.replace("trending_", "") as TrendingPeriod;
            if (period in next) next[period] = toForm(schedule);
          }
          return next;
        });
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "读取调度设置失败"))
      .finally(() => setLoading(false));
  }, []);

  function update(period: TrendingPeriod, patch: Partial<ScheduleForm>) {
    setForms((current) => ({ ...current, [period]: { ...current[period], ...patch } }));
    setSavedPeriod(null);
  }

  async function save(period: TrendingPeriod) {
    setSaving(period);
    setError(null);
    setSavedPeriod(null);
    try {
      const response = await api.saveCollectionSchedule(period, forms[period]);
      setSchedules((current) => current.map((item) =>
        item.job_type === response.schedule.job_type ? response.schedule : item,
      ));
      setSavedPeriod(period);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存调度设置失败");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="page-stack">
      <section className="settings-intro surface-card">
        <div className="settings-intro-icon"><CalendarClock size={21} /></div>
        <div>
          <h3>自动采集计划</h3>
          <p>日榜、周榜、月榜分别配置。关闭其中一项不会影响其他周期。</p>
          <small>自动任务仅在 GitScout 本地服务运行时执行；默认全部关闭，不会在首次启动后擅自请求 GitHub。</small>
        </div>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="schedule-cards">
        {periods.map((period) => {
          const form = forms[period.value];
          const saved = schedules.find((item) => item.job_type === "trending_" + period.value);
          return (
            <section className="surface-card schedule-card" key={period.value}>
              <div className="schedule-card-heading">
                <div>
                  <span className="eyebrow">{period.value.toUpperCase()} TRENDING</span>
                  <h3>{period.title}</h3>
                  <p>{period.subtitle}</p>
                </div>
                <label className="switch-control">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(event) => update(period.value, { enabled: event.target.checked })}
                  />
                  <span />
                  <small>{form.enabled ? "已启用" : "已关闭"}</small>
                </label>
              </div>

              <div className="schedule-fields">
                <label>
                  <span><Clock3 size={13} />执行时间</span>
                  <input type="time" value={form.time} onChange={(event) => update(period.value, { time: event.target.value })} />
                </label>
                {period.value === "weekly" && (
                  <label>
                    <span>执行星期</span>
                    <select value={form.weekday} onChange={(event) => update(period.value, { weekday: Number(event.target.value) })}>
                      {weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}
                    </select>
                  </label>
                )}
                {period.value === "monthly" && (
                  <label>
                    <span>每月日期</span>
                    <select value={form.day_of_month} onChange={(event) => update(period.value, { day_of_month: Number(event.target.value) })}>
                      {Array.from({ length: 28 }, (_, index) => index + 1).map((day) => <option key={day} value={day}>每月 {day} 日</option>)}
                    </select>
                  </label>
                )}
                <label className="timezone-field">
                  <span>时区</span>
                  <select value={form.timezone} onChange={(event) => update(period.value, { timezone: event.target.value })}>
                    {timezones.map((zone) => <option key={zone.value} value={zone.value}>{zone.label}</option>)}
                  </select>
                </label>
              </div>

              <div className="schedule-footer">
                <div>
                  <small>下次执行</small>
                  <strong>{form.enabled ? formatDate(saved?.next_run_at ?? null, form.timezone) : "已关闭"}</strong>
                  {saved?.last_run_at && <small>上次执行：{formatDate(saved.last_run_at, form.timezone)}</small>}
                </div>
                <button className="button button-primary" onClick={() => void save(period.value)} disabled={loading || saving !== null}>
                  {savedPeriod === period.value ? <Check size={14} /> : <Save size={14} />}
                  {saving === period.value ? "保存中…" : savedPeriod === period.value ? "已保存" : "保存设置"}
                </button>
              </div>
            </section>
          );
        })}
      </div>

      <div className="schedule-note">
        <strong>调度说明</strong>
        <span>周计划使用星期一至星期日；月计划可选每月 1—28 日，避免月底日期缺失。调度时间按所选时区计算，数据库统一保存 UTC 时间。</span>
      </div>
    </div>
  );
}
