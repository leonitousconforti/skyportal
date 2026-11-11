import { useCallback, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import { mapBlock } from "../components/filter/boom/block/blockTree";

export const useFilterFactories = () => {
  // Factory functions
  const createDefaultCondition = useCallback(
    () => ({
      id: uuidv4(),
      category: "condition",
      field: null,
      operator: null,
      value: "",
      createdAt: Date.now(),
    }),
    [],
  );

  const createDefaultBlock = useCallback(
    (logic = "And") => ({
      id: uuidv4(),
      category: "block",
      logic,
      children: [createDefaultCondition()],
      createdAt: Date.now(),
    }),
    [createDefaultCondition],
  );

  return {
    createDefaultCondition,
    createDefaultBlock,
  };
};

export const useFilterManipulation = (filters, setFilters) => {
  // Utility functions for filter manipulation
  const updateBlockLogic = useCallback(
    (blockId, logic) => {
      setFilters((prevFilters) =>
        mapBlock(prevFilters, blockId, (block) => ({ ...block, logic })),
      );
    },
    [setFilters],
  );

  const removeBlock = useCallback(
    (blockId, parentBlockId) => {
      if (parentBlockId === null) return;

      setFilters((prevFilters) =>
        mapBlock(prevFilters, parentBlockId, (block) => ({
          ...block,
          children: block.children.filter((child) => child.id !== blockId),
        })),
      );
    },
    [setFilters],
  );

  return {
    updateBlockLogic,
    removeBlock,
  };
};

export const useHoverState = (conditionId, filters) => {
  const [hoveredItems, setHoveredItems] = useState(new Set());

  const handleMouseEnter = (itemId) => {
    setHoveredItems((prev) => new Set([...prev, itemId]));
  };

  const handleMouseLeave = (itemId) => {
    setHoveredItems((prev) => {
      const newSet = new Set(prev);
      newSet.delete(itemId);
      return newSet;
    });
  };

  const getYoungestHoveredItem = () => {
    if (hoveredItems.size === 0) return null;

    const findAllItems = (blocks) => {
      let allItems = [];
      blocks?.forEach((block) => {
        const traverse = (item) => {
          allItems.push(item);
          if (item.category === "block" && item.children) {
            item.children.forEach(traverse);
          }
        };
        traverse(block);
      });
      return allItems;
    };

    const allItems = findAllItems(filters);
    const hoveredItemsArray = allItems.filter((item) =>
      hoveredItems.has(item.id),
    );

    if (hoveredItemsArray.length === 0) return null;

    return hoveredItemsArray.reduce((youngest, item) =>
      item.createdAt > youngest.createdAt ? item : youngest,
    );
  };

  const youngestHovered = getYoungestHoveredItem();
  const isYoungestHovered =
    youngestHovered && conditionId === youngestHovered.id;

  return {
    hoveredItems,
    isYoungestHovered,
    handleMouseEnter,
    handleMouseLeave,
  };
};
