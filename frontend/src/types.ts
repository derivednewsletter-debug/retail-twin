export type LayerKey = 'footTraffic' | 'awareness' | 'sentiment' | 'revenue'

export interface LocationConfig {
  id: 'A' | 'B' | 'C'
  enabled: boolean
}

export interface ScenarioConfig {
  category: string
  brand_name: string
  average_ticket: number
  store_size: number
  opening_time: number
  closing_time: number
  marketing_budget: number
  positioning: string
  target_demographic: string
  locations: LocationConfig[]
  marketing_channels: string[]
}

export interface Agent {
  id: number
  type: string
  x: number
  y: number
  status: string
  color: string
}

export interface LocationMetric {
  id: string
  name: string
  daily_revenue: number
  annual_revenue: number
  transactions: number
  repeat_rate: number
  conversion_rate: number
  foot_traffic: number
  market_share: number
  rent: number
  payback_months: number
  insight: string
}

export interface FeedItem {
  id: number
  name: string
  text: string
  sentiment: string
  time: string
  avatar: string
}

export interface CompetitorEvent {
  id: number
  competitor: string
  text: string
  kind: string
  time: string
}

export interface WeatherInfo {
  temperature_f: number
  condition: string
  wind_mph: number
  traffic_modifier: number
}

export interface TransitAlert {
  line: string
  status: string
  header: string
  severity: number
}

export interface TransitInfo {
  status: string
  traffic_modifier: number
  lines_affected: string[]
  alerts: TransitAlert[]
  last_updated: string
}

export interface DataSources {
  weather: string
  demographics: string
  nyc_open_data: string
  consumer_feed: string
}

export interface Snapshot {
  running: boolean
  complete?: boolean
  day: number
  hour: number
  progress: number
  active_agents: number
  foot_traffic: number
  daily_revenue: number
  transactions: number
  repeat_customers: number
  average_ticket: number
  conversion_rate: number
  market_share: number
  cac: number
  roi: number
  locations: LocationMetric[]
  feed: FeedItem[]
  competitor_events: CompetitorEvent[]
  agents: Agent[]
  layer_values: Record<LayerKey, number>
  weather?: WeatherInfo
  transit?: TransitInfo
  real_world_modifier?: number
  data_sources?: DataSources
}
