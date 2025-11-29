'use client';

import React from 'react';
import { motion } from 'motion/react';
import { cn } from '@/lib/utils';

const MotionDiv = motion.create('div');

interface OrderItem {
  product_id: string;
  product_name: string;
  quantity: number;
  price: number;
  item_total: number;
  size?: string;
}

interface Order {
  id: string;
  items: OrderItem[];
  total: number;
  currency: string;
  status: string;
  created_at: string;
}

interface LastOrderProps {
  order?: Order | null;
  className?: string;
}

export function LastOrder({ order, className }: LastOrderProps) {
  if (!order || !Array.isArray(order.items) || order.items.length === 0) return null;

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className={cn('pointer-events-auto', className)}
    >
      <div className="bg-primary/10 backdrop-blur-md border border-primary/30 rounded-lg shadow-lg p-4">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold text-foreground">Order Confirmed</h3>
          <span className="text-[10px] bg-primary/20 text-primary px-2 py-1 rounded">{order.status ?? 'unknown'}</span>
        </div>

        <div className="space-y-2 mb-3">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Order ID:</span>
            <span className="font-mono text-foreground">{order.id ?? '-'}</span>
          </div>
        </div>

        <div className="border-t border-input/30 pt-2 space-y-2">
          {order.items.map((item, index) => (
            <div key={index} className="flex justify-between items-start text-xs">
              <div className="flex-1">
                <span className="text-foreground">{item.product_name}</span>
                {item.size && <span className="text-muted-foreground ml-2">({item.size})</span>}
                <div className="text-[10px] text-muted-foreground">Qty: {item.quantity} × ₹{item.price}</div>
              </div>
              <span className="text-foreground font-medium whitespace-nowrap ml-2">₹{item.item_total}</span>
            </div>
          ))}
        </div>

        <div className="border-t border-primary/30 mt-3 pt-2 flex justify-between items-center">
          <span className="text-sm font-semibold text-foreground">Total:</span>
          <span className="text-lg font-bold text-primary">₹{order.total ?? 0}</span>
        </div>

        <div className="text-[10px] text-muted-foreground mt-2 text-center">
          {order.created_at ? new Date(order.created_at).toLocaleString() : ''}
        </div>
      </div>
    </MotionDiv>
  );
}

export default LastOrder;
