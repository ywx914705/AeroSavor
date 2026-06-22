/** 判断用户查询是否暗示"附近"（需要GPS定位才能精准推荐）。 */

const NEARBY_PATTERN = /附近|周边|周围|就近|离我近/

/** 检查查询是否包含"附近"类关键词。 */
export function isNearbyQuery(query: string): boolean {
  return NEARBY_PATTERN.test(query)
}
