import { useQuery } from "@tanstack/react-query";
import { fetchItems, fetchMeta, fetchBriefing, fetchMarkers, fetchInsights, type FetchItemsParams, type MetaResponse, type BriefingResponse, type MapMarkerData, type InsightsResponse } from "./api";
import type { Item } from "./mock-data";

export function useItems(params?: FetchItemsParams) {
  return useQuery<Item[]>({
    queryKey: ["items", params ?? {}],
    queryFn: () => fetchItems(params),
    staleTime: 60_000,
  });
}

export function useMeta() {
  return useQuery<MetaResponse>({
    queryKey: ["meta"],
    queryFn: fetchMeta,
    staleTime: 300_000,
  });
}

export function useBriefing() {
  return useQuery<BriefingResponse>({
    queryKey: ["briefing"],
    queryFn: fetchBriefing,
    staleTime: 120_000,
  });
}

export function useMarkers() {
  return useQuery<MapMarkerData[]>({
    queryKey: ["markers"],
    queryFn: fetchMarkers,
    staleTime: 120_000,
  });
}

export function useInsights() {
  return useQuery<InsightsResponse>({
    queryKey: ["insights"],
    queryFn: fetchInsights,
    staleTime: 300_000,
  });
}
