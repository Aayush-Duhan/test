import { memo, type ReactNode } from 'react';
import { classNames } from '~/utils/classNames';

type IconSize = 'sm' | 'md' | 'lg' | 'xl' | 'xxl';

interface BaseIconButtonProps {
  size?: IconSize;
  className?: string;
  iconClassName?: string;
  disabledClassName?: string;
  title?: string;
  disabled?: boolean;
  onClick?: (event: React.MouseEvent<HTMLButtonElement, MouseEvent>) => void;
}

type IconButtonWithoutChildrenProps = {
  icon: string | ReactNode;
  children?: undefined;
} & BaseIconButtonProps;

type IconButtonWithChildrenProps = {
  icon?: undefined;
  children: string | JSX.Element | JSX.Element[];
} & BaseIconButtonProps;

type IconButtonProps = IconButtonWithoutChildrenProps | IconButtonWithChildrenProps;

export const IconButton = memo(
  ({
    icon,
    size = 'xl',
    className,
    iconClassName,
    disabledClassName,
    disabled = false,
    title,
    onClick,
    children,
  }: IconButtonProps) => {
    return (
      <button
        className={classNames(
          'flex items-center text-bolt-item-content-default bg-transparent enabled:hover:text-bolt-item-content-active rounded-md p-1 enabled:hover:bg-bolt-item-bg-active disabled:cursor-not-allowed',
          {
            [classNames('opacity-30', disabledClassName)]: disabled,
          },
          className,
        )}
        title={title}
        disabled={disabled}
        onClick={(event) => {
          if (disabled) {
            return;
          }

          onClick?.(event);
        }}
      >
        {children
          ? children
          : typeof icon === 'string'
            ? <div className={classNames(icon, getIconSize(size), iconClassName)}></div>
            : <span className={classNames(getIconSize(size), iconClassName)}>{icon}</span>}
      </button>
    );
  },
);

function getIconSize(size: IconSize) {
  if (size === 'sm') {
    return 'text-sm';
  } else if (size === 'md') {
    return 'text-md';
  } else if (size === 'lg') {
    return 'text-lg';
  } else if (size === 'xl') {
    return 'text-xl';
  } else {
    return 'text-2xl';
  }
}
