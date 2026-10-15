// Reconstructed from Rain (NPUA80719) Assembly-CSharp AOT code (work/poc/RegionBox.decomp.txt). Phase 3 iteration 2.
// Runtime layout (verified, E52): refs first (m_RegionTriggerArray +0x10, m_LoadingInfo +0x14), then declaration order:
// bools +0x18..+0x21, m_Index +0x24, m_IndexX +0x28, m_IndexZ +0x29, m_Count +0x2C, m_HasLoadingInfo +0x30.
// INFERENCE markers: virtual calls whose vtable slots are not yet resolved (E53) are named from call context.
using System;
using UnityEngine;

public class RegionBox : MonoBehaviour
{
    public bool m_IsEnable;
    [NonSerialized] public bool m_IsEntry;
    [NonSerialized] public bool m_Is1st = true;            // ctor: +0x1A = 1
    [NonSerialized] public bool m_IsEnableRender;
    [NonSerialized] public bool m_IsEnableLogic;
    [NonSerialized] public bool m_ChgEnableRender;
    [NonSerialized] public bool m_ChgEnableLogic;
    [NonSerialized] public bool m_EnableRenderOld;
    [NonSerialized] public bool m_EnableLogicOld;
    private bool m_HasArray;
    public int m_Index = -1;                               // ctor: +0x24 = -1
    public byte m_IndexX;
    public byte m_IndexZ;
    public int m_Count;
    public RegionTrigger[] m_RegionTriggerArray;
    public MapLoader.AreaData m_LoadingInfo;
    private bool m_HasLoadingInfo;

    // 0x0600156F
    public int GetTotal() { return m_HasArray ? m_RegionTriggerArray.Length : 0; }

    // 0x06001570
    private void Awake() { CheckArray(); }

    // 0x06001571: compacts the array (moves live entries from the end into null holes), counts live entries.
    public int CheckArray()
    {
        m_Count = 0;
        m_HasArray = m_RegionTriggerArray != null;
        if (m_HasArray)
        {
            int lastLive = -1;
            for (int i = m_RegionTriggerArray.Length - 1; i >= 0; i--)
            {
                if (!m_RegionTriggerArray[i])
                {
                    if (lastLive >= 0)
                    {
                        m_RegionTriggerArray[i] = m_RegionTriggerArray[lastLive];
                        m_RegionTriggerArray[lastLive] = null;
                        do { lastLive--; } while (lastLive >= 0 && !m_RegionTriggerArray[lastLive]);
                    }
                }
                else
                {
                    m_Count++;
                    if (lastLive < 0) lastLive = i;
                }
            }
        }
        m_HasLoadingInfo = m_LoadingInfo != null;
        if (m_HasLoadingInfo) m_HasLoadingInfo = m_LoadingInfo.isValid();
        if (!m_HasLoadingInfo) m_LoadingInfo = null;
        return m_Count;
    }

    // 0x06001572
    public void Release()
    {
        if (m_RegionTriggerArray != null)
        {
            int i = 0;
            while (i < m_Count)
            {
                RegionTrigger t = m_RegionTriggerArray[i];
                if (t) t.Release();                         // INFERENCE (E53): vtable +0x4C, 1 arg
                RegionTrigger cur = m_RegionTriggerArray[i];
                if (!cur || cur.Equals(t)) i++;             // INFERENCE (E53): vtable +0x30, (cur, t) -> bool
            }
            RuntimeMisc.Release(m_RegionTriggerArray);
            m_RegionTriggerArray = null;
            m_HasArray = false;
        }
        m_LoadingInfo = null;
    }

    // 0x06001573
    private void OnDestroy() { Release(); }

    // 0x06001574: append (grow by 8 when full); returns false if already present.
    public bool AddRegionTrigger(RegionTrigger trigger, bool isEdit)
    {
        int len = 0, newLen = 8;
        if (m_HasArray)
        {
            len = m_RegionTriggerArray.Length;
            int i;
            for (i = 0; i < m_Count; i++)
                if (m_RegionTriggerArray[i] == trigger) return false;   // reference compare (asm: cmp on pointers)
            if (i < len)
            {
                m_RegionTriggerArray[i] = trigger;
                trigger.SetParent(this);
                m_Count++;
                m_Is1st = true;
                return true;
            }
            newLen = len + 8;
        }
        RegionTrigger[] grown = new RegionTrigger[newLen];
        if (m_HasArray) m_RegionTriggerArray.CopyTo(grown, 0);
        grown[len] = trigger;
        trigger.SetParent(this);
        m_RegionTriggerArray = grown;
        m_HasArray = true;
        m_Count = len + 1;
        m_Is1st = true;
        return true;
    }

    // 0x06001575: remove by swapping the last live entry into the hole.
    public void SubRegionTrigger(RegionTrigger trigger)
    {
        trigger.ClearParent(this);
        if (!m_HasArray) return;
        for (int i = 0; i < m_Count; i++)
        {
            if (m_RegionTriggerArray[i] == trigger)
            {
                m_Count--;
                int hole = i;
                if (i < m_Count) { m_RegionTriggerArray[i] = m_RegionTriggerArray[m_Count]; hole = m_Count; }
                m_RegionTriggerArray[hole] = null;
                return;
            }
        }
    }

    // 0x06001576
    public void OnRegionTriggerEnter()
    {
        if (!m_IsEnable && m_HasLoadingInfo) MapLoader.EntryLoading(m_LoadingInfo, this);
        m_IsEnable = true;
        m_Is1st = false;
        if (!m_HasArray) return;
        for (int i = 0; i < m_Count; i++)
        {
            RegionTrigger t = m_RegionTriggerArray[i];
            if (t.gameObject.active && t.enabled) t.OnRegionTriggerEnter(this);   // INFERENCE (E53): vtable +0x48
        }
    }

    // 0x06001577
    public void OnRegionTriggerExit()
    {
        m_IsEnable = false;
        m_Is1st = false;
        m_EnableRenderOld = false;
        m_EnableLogicOld = false;
        if (!m_HasArray) return;
        for (int i = 0; i < m_Count; i++)
        {
            RegionTrigger t = m_RegionTriggerArray[i];
            if (t.gameObject.active && t.enabled) t.OnRegionTriggerExit(this);    // INFERENCE (E53): vtable +0x44
        }
    }
}
