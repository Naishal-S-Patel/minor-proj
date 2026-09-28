import { useState } from "react";
import { useDispatch } from "react-redux";
import type { AppDispatch } from "../../store";
import type { ActionItem } from "../../api/client";
import { toggleActionItem } from "../../store/meetingsSlice";

interface ActionItemsTableProps {
  meetingId: string;
  actionItems: ActionItem[];
}

/**
 * Renders action items with a completion checkbox per row.
 *
 * Uses OPTIMISTIC updates: clicking a checkbox flips its visual state
 * immediately (via local `pendingOverrides` state), before the network
 * request even resolves. This is the right call for a frequent, low-stakes,
 * easily-reversible action like checking off a task -- making someone wait
 * 200-500ms staring at an unchanged checkbox on every single click would
 * feel sluggish for something this minor. If the request fails, the
 * optimistic change is rolled back and the row is visually flagged so the
 * user knows their click didn't actually stick.
 *
 * Local optimistic state is layered ON TOP of the meeting prop (not a
 * replacement for it): `actionItems` still comes from Redux/the server as
 * the source of truth, and `pendingOverrides` only exists to bridge the
 * gap between "user clicked" and "server confirmed," then gets cleared once
 * the real prop catches up.
 */
export function ActionItemsTable({ meetingId, actionItems }: ActionItemsTableProps) {
  const dispatch = useDispatch<AppDispatch>();
  // Maps item id -> optimistic done state, only for items with an
  // in-flight or just-failed toggle. Cleared once the real `actionItems`
  // prop reflects the same value (see the render logic below), so this
  // map never permanently drifts from reality.
  const [pendingOverrides, setPendingOverrides] = useState<Record<string, boolean>>({});
  const [failedIds, setFailedIds] = useState<Set<string>>(new Set());

  if (actionItems.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">&#9745;</div>
        <p>No action items extracted from this meeting.</p>
      </div>
    );
  }

  const handleToggle = async (item: ActionItem) => {
    const optimisticDone = !getDisplayedDone(item);

    setPendingOverrides((prev) => ({ ...prev, [item.id]: optimisticDone }));
    setFailedIds((prev) => {
      const next = new Set(prev);
      next.delete(item.id);
      return next;
    });

    try {
      await dispatch(
        toggleActionItem({ meetingId, itemId: item.id, done: optimisticDone }),
      ).unwrap();
      // On success, the Redux store's `selected.action_items` now reflects
      // the new value (see meetingsSlice.ts's toggleActionItem.fulfilled),
      // which flows back into this component's `actionItems` prop on the
      // next render -- at that point getDisplayedDone() reads the real
      // value directly and this override is no longer needed. We clear it
      // explicitly rather than waiting for a prop-vs-override comparison,
      // since immediately clearing avoids a render where both are briefly
      // inconsistent.
      setPendingOverrides((prev) => {
        const { [item.id]: _removed, ...rest } = prev;
        return rest;
      });
    } catch {
      // Roll back to the PRE-click value and flag this row so the user
      // gets visible feedback that their click didn't take effect --
      // silently reverting with no indication would be confusing (it'd
      // just look like the click did nothing, with no explanation why).
      setPendingOverrides((prev) => {
        const { [item.id]: _removed, ...rest } = prev;
        return rest;
      });
      setFailedIds((prev) => new Set(prev).add(item.id));
    }
  };

  function getDisplayedDone(item: ActionItem): boolean {
    return item.id in pendingOverrides ? pendingOverrides[item.id] : item.done;
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th style={{ width: "40px" }}></th>
            <th>Person</th>
            <th>Task</th>
            <th>Deadline</th>
          </tr>
        </thead>
        <tbody>
          {actionItems.map((item) => {
            const isDone = getDisplayedDone(item);
            const isPending = item.id in pendingOverrides;
            const didFail = failedIds.has(item.id);

            return (
              <tr key={item.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={isDone}
                    onChange={() => handleToggle(item)}
                    aria-label={`Mark "${item.task}" as ${isDone ? "not done" : "done"}`}
                    style={{
                      width: "16px",
                      height: "16px",
                      cursor: "pointer",
                      accentColor: "var(--color-accent)",
                      opacity: isPending ? 0.5 : 1,
                    }}
                  />
                </td>
                <td style={{ fontWeight: 500 }}>{item.person}</td>
                <td
                  style={{
                    textDecoration: isDone ? "line-through" : "none",
                    color: isDone ? "var(--color-text-muted)" : "inherit",
                    transition: "color 0.2s, text-decoration-color 0.2s",
                  }}
                >
                  {item.task}
                  {didFail && (
                    <span
                      style={{
                        display: "block",
                        fontSize: "0.75rem",
                        color: "var(--color-error)",
                        marginTop: "0.125rem",
                      }}
                    >
                      Couldn't save — try again
                    </span>
                  )}
                </td>
                <td>
                  {item.deadline ? (
                    <span className="deadline-badge present">{item.deadline}</span>
                  ) : (
                    <span className="deadline-badge absent">No deadline</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
