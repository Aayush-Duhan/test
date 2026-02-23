import { AnimatePresence, motion } from 'framer-motion';
import { memo, useMemo } from 'react';
import {
    Circle,
    Check,
    X,
    Loader2,
    Zap,
    FolderOpen,
    Table2,
    ArrowRightLeft,
    Bug,
    ShieldCheck,
} from 'lucide-react';
import styles from './WorkflowProgress.module.scss';

/**
 * Workflow step status type.
 */
type StepStatus = 'pending' | 'running' | 'completed' | 'failed';

/**
 * A single workflow step as received from the data stream.
 */
interface WorkflowStep {
    id: string;
    name: string;
    status: StepStatus;
    message?: string;
}

/**
 * Workflow progress data sent via the data-stream custom data protocol.
 * Event type: `data-workflow-status`
 */
interface WorkflowStatusData {
    runId: string;
    status: 'running' | 'completed' | 'failed';
    currentStep: string | null;
    steps: WorkflowStep[];
}

interface WorkflowProgressProps {
    data: WorkflowStatusData;
}

/** Maps step IDs to their icons. */
const STEP_ICONS: Record<string, React.ComponentType<any>> = {
    init_project: Zap,
    add_source_code: FolderOpen,
    apply_schema_mapping: Table2,
    convert_code: ArrowRightLeft,
    execute_sql: Zap,
    self_heal: Bug,
    validate: ShieldCheck,
    human_review: Circle,
    finalize: Check,
};

/**
 * WorkflowProgress — renders a vertical step timeline for the SCAI workflow.
 *
 * Receives `data-workflow-status` custom data events from the backend
 * and displays each step with its status icon, name, and optional message.
 */
export const WorkflowProgress = memo(({ data }: WorkflowProgressProps) => {
    const { steps, status: overallStatus } = data;

    const statusLabel = useMemo(() => {
        switch (overallStatus) {
            case 'running':
                return 'In Progress';
            case 'completed':
                return 'Completed';
            case 'failed':
                return 'Failed';
            default:
                return overallStatus;
        }
    }, [overallStatus]);

    return (
        <div className={styles.workflowProgress}>
            {/* Header */}
            <div className={styles.workflowHeader}>
                <div className={styles.workflowIcon}>
                    <Zap size={14} />
                </div>
                <div>
                    <div className={styles.workflowTitle}>SCAI Conversion Workflow</div>
                    <div className={styles.workflowSubtitle}>Converting codebase to Snowflake</div>
                </div>
                <div className={styles.statusBadge} data-status={overallStatus}>
                    {overallStatus === 'running' && <Loader2 size={10} className="animate-spin" />}
                    {overallStatus === 'completed' && <Check size={10} />}
                    {overallStatus === 'failed' && <X size={10} />}
                    {statusLabel}
                </div>
            </div>

            {/* Steps */}
            <div className={styles.stepsList}>
                <AnimatePresence>
                    {steps.map((step, index) => (
                        <motion.div
                            key={step.id}
                            className={styles.stepItem}
                            data-status={step.status}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.05, duration: 0.2 }}
                        >
                            <StepStatusIcon status={step.status} stepId={step.id} />
                            <div className={styles.stepContent}>
                                <div className={styles.stepName}>{step.name}</div>
                                {step.message && (
                                    <motion.div
                                        className={styles.stepMessage}
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 0.85 }}
                                        transition={{ duration: 0.3 }}
                                    >
                                        {step.message}
                                    </motion.div>
                                )}
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </div>
    );
});

/** Renders the step status icon with appropriate styling. */
function StepStatusIcon({ status, stepId }: { status: StepStatus; stepId: string }) {
    const StepIcon = STEP_ICONS[stepId] || Circle;

    return (
        <div className={styles.stepIcon} data-status={status}>
            {status === 'running' ? (
                <Loader2 size={12} className="animate-spin" />
            ) : status === 'completed' ? (
                <Check size={12} />
            ) : status === 'failed' ? (
                <X size={12} />
            ) : (
                <StepIcon size={10} />
            )}
        </div>
    );
}
