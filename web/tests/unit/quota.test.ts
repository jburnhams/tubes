import { describe, expect, it } from 'vitest'
import { quotaNoKey, quotaSpent, quotaUnused, quotaUsage } from '../../src/mocks/fixtures'
import { dayLabel, describeQuota, mostlyOn, purposeLabel, units } from '../../src/screens/QuotaScreen'

describe('the quota page’s words', () => {
  it('names each purpose, and a new one by its name', () => {
    expect(purposeLabel('sync')).toBe('Syncing channels')
    expect(purposeLabel('related')).toBe('Finding related channels')
    expect(purposeLabel('something-new')).toBe('something-new')
  })

  it('counts units, one and many', () => {
    expect(units(1)).toBe('1 unit')
    expect(units(10_000)).toBe('10,000 units')
  })

  it('finds what each state says first', () => {
    expect(describeQuota(quotaUsage)).toMatch(/^1,712\sunits of 10,000 used today, 8,288\sunits left until the reset at .+\. Most went on syncing channels\.$/)
    expect(describeQuota(quotaSpent)).toMatch(/^YouTube refused a call at .+ because the key’s quota is spent/)
    expect(describeQuota(quotaUnused)).toMatch(/^Nothing has been asked of YouTube today/)
    expect(describeQuota(quotaNoKey)).toMatch(/^The server has no YouTube key/)
    expect(describeQuota({ ...quotaUsage, configured: false })).toMatch(/^1,712/)                    // the key went, but today was counted
  })

  it('warns as the quota runs low, then nearly out', () => {
    const at = (used: number) => describeQuota({ ...quotaUsage, used, remaining: 10_000 - used })
    expect(at(7_999)).not.toMatch(/Running low/)
    expect(at(8_000)).toMatch(/Running low: a sync may stop part way and carry on after the reset\.$/)
    expect(at(9_600)).toMatch(/Nearly spent: /)
  })

  it('labels days and what they mostly went on', () => {
    expect(dayLabel('2026-11-09')).toBe('9 Nov')
    expect(mostlyOn(quotaUsage.days[0])).toBe('Syncing channels')
    expect(mostlyOn({ ...quotaUsage.days[0], purposes: { recheck: 5, add: 5 } })).toBe('Adding channels and videos')         // a tie goes by name
    expect(mostlyOn(quotaNoKey.days[0])).toBeNull()
  })
})
