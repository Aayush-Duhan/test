import * as RadixDialog from '@radix-ui/react-dialog';
import { motion, type Variants } from 'framer-motion';
import React, { memo, type ReactNode } from 'react';
import { classNames } from '~/utils/classNames';
import { cubicEasingFn } from '~/utils/easings';
import { IconButton } from './IconButton';

export { Close as DialogClose, Root as DialogRoot } from '@radix-ui/react-dialog';

const transition = {
  duration: 0.15,
  ease: cubicEasingFn,
};

export const dialogBackdropVariants = {
  closed: {
    opacity: 0,
    transition,
  },
  open: {
    opacity: 1,
    transition,
  },
} satisfies Variants;

export const dialogVariants = {
  closed: {
    x: '-50%',
    y: '-40%',
    scale: 0.96,
    opacity: 0,
    transition,
  },
  open: {
    x: '-50%',
    y: '-50%',
    scale: 1,
    opacity: 1,
    transition,
  },
} satisfies Variants;

interface DialogButtonProps {
  type: 'primary' | 'secondary' | 'danger';
  children: ReactNode;
  onClick?: (event: React.UIEvent) => void;
}

export const DialogButton = memo(({ type, children, onClick }: DialogButtonProps) => {
  return (
    <button
      className={classNames(
        'inline-flex h-[35px] items-center justify-center rounded-lg px-4 text-sm leading-none text-white focus:outline-none',
        {
          'bg-bolt-elements-button-primary-background hover:bg-bolt-elements-button-primary-backgroundHover':
            type === 'primary',
          'bg-bolt-elements-button-secondary-background hover:bg-bolt-elements-button-secondary-backgroundHover':
            type === 'secondary',
          'bg-bolt-elements-button-danger-background hover:bg-bolt-elements-button-danger-backgroundHover':
            type === 'danger',
        },
      )}
      onClick={onClick}
    >
      {children}
    </button>
  );
});

export const DialogTitle = memo(({ className, children, ...props }: RadixDialog.DialogTitleProps) => {
  return (
    <RadixDialog.Title
      className={classNames(
        'px-5 py-4 flex items-center justify-between border-b border-bolt-border text-lg font-semibold leading-6 text-bolt-text-primary',
        className,
      )}
      {...props}
    >
      {children}
    </RadixDialog.Title>
  );
});

export const DialogDescription = memo(({ className, children, ...props }: RadixDialog.DialogDescriptionProps) => {
  return (
    <RadixDialog.Description
      className={classNames('px-5 py-4 text-bolt-text-primary text-md', className)}
      {...props}
    >
      {children}
    </RadixDialog.Description>
  );
});

interface DialogProps {
  children: ReactNode | ReactNode[];
  className?: string;
  onBackdrop?: (event: React.UIEvent) => void;
  onClose?: (event: React.UIEvent) => void;
}

export const Dialog = memo(({ className, children, onBackdrop, onClose }: DialogProps) => {
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay onClick={onBackdrop} asChild>
        <motion.div
          className="bg-black/50 fixed inset-0 z-max"
          initial="closed"
          animate="open"
          exit="closed"
          variants={dialogBackdropVariants}
        />
      </RadixDialog.Overlay>
      <RadixDialog.Content asChild>
        <motion.div
          className={classNames(
            'fixed top-[50%] left-[50%] z-max max-h-[80vh] w-[88vw] max-w-[420px] border border-bolt-border rounded-lg bg-bolt-bg-depth-2 shadow-lg focus:outline-none overflow-y-auto',
            className,
          )}
          initial="closed"
          animate="open"
          exit="closed"
          variants={dialogVariants}
        >
          {children}
          <RadixDialog.Close asChild onClick={onClose}>
            <IconButton icon="i-ph:x" className="absolute top-[10px] right-[10px]" />
          </RadixDialog.Close>
        </motion.div>
      </RadixDialog.Content>
    </RadixDialog.Portal>
  );
});
